import pytest

from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import ArtifactLocalTool, TodoLocalTool, WorkspaceLocalTool
from aithru_agent.domain import AgentRunStatus
from aithru_agent.harness import HarnessRunPaused
from aithru_agent.harness.drivers.pydantic_ai.tool_bridge import PydanticAIToolBridge
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_calls_capability_router_and_emits_events() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Read file",
        workspace_id=workspace.id,
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/notes.md",
        content="hello",
        media_type="text/plain",
    )
    context = AgentRunContext(
        run_id=run.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    router = AithruCapabilityRouter(
        adapters=[WorkspaceLocalTool(store), TodoLocalTool(store), ArtifactLocalTool(store)],
        policy=ToolPolicy(require_approval_for_risk=[]),
    )
    bridge = PydanticAIToolBridge(
        run=run,
        run_context=context,
        event_writer=writer,
        capability_router=router,
        store=store,
    )

    result = await bridge.call_tool(
        tool_name="workspace.read_file",
        tool_call_id="tc_1",
        tool_input={"path": "/notes.md"},
    )
    events = await event_store.list_by_run(run.id)

    assert result == {"path": "/notes.md", "content": "hello", "media_type": "text/plain"}
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "workspace.file.read",
        "tool.completed",
    ]


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_records_approval_and_pauses_run() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Write file",
        workspace_id=workspace.id,
    )
    context = AgentRunContext(
        run_id=run.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    router = AithruCapabilityRouter(
        adapters=[WorkspaceLocalTool(store), TodoLocalTool(store), ArtifactLocalTool(store)],
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    bridge = PydanticAIToolBridge(
        run=run,
        run_context=context,
        event_writer=writer,
        capability_router=router,
        store=store,
    )

    with pytest.raises(HarnessRunPaused):
        await bridge.call_tool(
            tool_name="workspace.write_file",
            tool_call_id="tc_approval",
            tool_input={"path": "/notes.md", "content": "hello"},
        )
    paused_run = await store.get_run(run.id)
    approvals = await store.list_approvals()
    events = await event_store.list_by_run(run.id)

    assert paused_run is not None
    assert paused_run.status == AgentRunStatus.WAITING_APPROVAL
    assert paused_run.current_approval_id == approvals[0].id
    assert [event.type for event in events] == [
        "tool.proposed",
        "approval.requested",
        "run.paused",
    ]
