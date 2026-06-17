import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import ArtifactLocalTool, TodoLocalTool, WorkspaceLocalTool
from aithru_agent.domain import (
    AgentRunStatus,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
)
from aithru_agent.harness import HarnessRunPaused
from aithru_agent.harness.drivers.pydantic_ai.tool_bridge import PydanticAIToolBridge
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


class SecretEchoTool:
    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="secret.echo",
                kind="local_tool",
                description="Echo sensitive fields for redaction testing.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_level="safe",
                required_scopes=[],
                approval_policy="never",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        input_data = request.input if isinstance(request.input, dict) else {}
        return AgentToolCallResult(
            status="completed",
            output={
                "token": input_data.get("token"),
                "nested": {"password": "pw_123"},
                "safe": "visible",
            },
            redaction="none",
        )


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
async def test_pydantic_tool_bridge_redacts_sensitive_stream_payload_fields() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Use secret",
        workspace_id=workspace.id,
    )
    context = AgentRunContext(
        run_id=run.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    bridge = PydanticAIToolBridge(
        run=run,
        run_context=context,
        event_writer=writer,
        capability_router=AithruCapabilityRouter(
            adapters=[SecretEchoTool()],
            policy=ToolPolicy(require_approval_for_risk=[]),
        ),
        store=store,
    )

    result = await bridge.call_tool(
        tool_name="secret.echo",
        tool_call_id="tc_secret",
        tool_input={"token": "tok_123", "safe": "visible"},
    )
    events = await event_store.list_by_run(run.id)
    proposed = next(event for event in events if event.type == "tool.proposed")
    completed = next(event for event in events if event.type == "tool.completed")

    assert result == {
        "token": "tok_123",
        "nested": {"password": "pw_123"},
        "safe": "visible",
    }
    assert proposed.payload["input"] == {"token": "[REDACTED]", "safe": "visible"}
    assert proposed.redaction == "partial"
    assert completed.payload["output"] == {
        "token": "[REDACTED]",
        "nested": {"password": "[REDACTED]"},
        "safe": "visible",
    }
    assert completed.redaction == "partial"


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


@pytest.mark.asyncio
async def test_pydantic_approval_resume_executes_persisted_tool_call() -> None:
    runtime = create_agent_runtime(policy=ToolPolicy(require_approval_for_risk=["write"]))
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Write file",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    context = AgentRunContext(
        run_id=run.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    bridge = PydanticAIToolBridge(
        run=run,
        run_context=context,
        event_writer=runtime.event_writer,
        capability_router=runtime.capability_router,
        store=runtime.store,
    )

    with pytest.raises(HarnessRunPaused):
        await bridge.call_tool(
            tool_name="workspace.write_file",
            tool_call_id="tc_resume",
            tool_input={"path": "/notes.md", "content": "hello"},
        )
    approval = (await runtime.store.list_approvals())[0]

    resumed = await runtime.runner.resume_run(
        run.id,
        approval_id=approval.id,
        decision="approved",
        comment="ok",
    )
    file = await runtime.store.read_workspace_file(workspace.id, "/notes.md")
    events = await runtime.event_store.list_by_run(run.id)

    assert resumed.status == AgentRunStatus.COMPLETED
    assert file.content == "hello"
    assert [event.type for event in events][-8:] == [
        "approval.resolved",
        "run.resumed",
        "tool.started",
        "workspace.file.created",
        "tool.completed",
        "model.completed",
        "message.completed",
        "run.completed",
    ]
