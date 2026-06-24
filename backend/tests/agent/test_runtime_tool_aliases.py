import pytest
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import DeferredToolRequests

from aithru_agent.agent import AgentRuntime, PydanticAgentDeps
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import WorkspaceLocalTool
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_deferred_approval_records_internal_tool_name_for_safe_model_alias() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Write a file.",
        workspace_id=workspace.id,
    )
    run = await store.update_run(run.id, status="running")
    deps = PydanticAgentDeps(
        run=run,
        run_context=AgentRunContext(
            run_id=run.id,
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id=workspace.id,
            scopes=["*"],
        ),
        event_writer=writer,
        capability_router=AithruCapabilityRouter(
            adapters=[WorkspaceLocalTool(store)],
            policy=ToolPolicy(require_approval_for_risk=["write"]),
        ),
        store=store,
    )
    deps.tool_name_aliases["workspace_write_file"] = "workspace.write_file"

    await AgentRuntime()._pause_for_deferred_approval(
        deps,
        DeferredToolRequests(
            approvals=[
                ToolCallPart(
                    tool_name="workspace_write_file",
                    args={"path": "/notes.md", "content": "hello"},
                    tool_call_id="tc_1",
                )
            ]
        ),
        [],
    )

    approvals = [
        approval
        for approval in await store.list_approvals()
        if approval.run_id == run.id
    ]
    events = await event_store.list_by_run(run.id)

    assert approvals[0].tool_name == "workspace.write_file"
    assert [
        event.payload["tool_name"]
        for event in events
        if event.type in {"tool.proposed", "approval.requested", "run.paused"}
    ] == ["workspace.write_file", "workspace.write_file", "workspace.write_file"]
