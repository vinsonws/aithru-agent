import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import ArtifactLocalTool, TodoLocalTool, WorkspaceLocalTool
from aithru_agent.domain import (
    AgentRunStatus,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.settings import AgentSettings
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


class ToolContext:
    def __init__(self, tool_call_id: str, *, approved: bool = False) -> None:
        self.tool_call_id = tool_call_id
        self.run_step = 0
        self.tool_call_approved = approved


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
        deps=PydanticAgentDeps(
            run=run,
            run_context=context,
            event_writer=writer,
            capability_router=router,
            store=store,
        ),
    )

    result = await bridge.call_tool(
        ToolContext("tc_1"),
        tool_name="workspace.read_file",
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
        deps=PydanticAgentDeps(
            run=run,
            run_context=context,
            event_writer=writer,
            capability_router=AithruCapabilityRouter(
                adapters=[SecretEchoTool()],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    result = await bridge.call_tool(
        ToolContext("tc_secret"),
        tool_name="secret.echo",
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
async def test_pydantic_tool_bridge_rejects_non_deferred_approval_required_tool() -> None:
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
        deps=PydanticAgentDeps(
            run=run,
            run_context=context,
            event_writer=writer,
            capability_router=router,
            store=store,
        ),
    )

    with pytest.raises(AgentError) as exc_info:
        await bridge.call_tool(
            ToolContext("tc_approval"),
            tool_name="workspace.write_file",
            tool_input={"path": "/notes.md", "content": "hello"},
        )
    paused_run = await store.get_run(run.id)
    approvals = await store.list_approvals()
    events = await event_store.list_by_run(run.id)

    assert paused_run is not None
    assert paused_run.status != AgentRunStatus.WAITING_APPROVAL
    assert approvals == []
    assert exc_info.value.code == "TOOL_APPROVAL_NOT_DEFERRED"
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.failed",
    ]


@pytest.mark.asyncio
async def test_pydantic_approval_resume_executes_persisted_tool_call() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["workspace.write_file"], custom_output_text="done")
        ),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write file",
        scopes=["*"],
    )
    approval = (await runtime.store.list_approvals())[0]

    resumed = await runtime.runner.resume_run(
        run.id,
        approval_id=approval.id,
        decision="approved",
        comment="ok",
    )
    file = await runtime.store.read_workspace_file(run.workspace_id, "/a")
    events = await runtime.event_store.list_by_run(run.id)

    assert resumed.status == AgentRunStatus.COMPLETED
    assert file.content == "a"
    assert [event.type for event in events][-11:] == [
        "approval.resolved",
        "run.resumed",
        "tool.started",
        "workspace.file.created",
        "tool.completed",
        "message.delta",
        "message.delta",
        "model.usage",
        "model.completed",
        "message.completed",
        "run.completed",
    ]
