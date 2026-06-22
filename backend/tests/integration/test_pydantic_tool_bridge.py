import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import (
    AgentRuntime,
    PydanticAgentDeps,
    RunPausedForExternalApproval,
    RunPausedForExternalRun,
)
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import (
    AgentRunContext,
    AithruCapabilityRouter,
    ExternalToolAdapter,
    ToolPolicy,
    WorkflowCapabilityAdapter,
    WorkflowCapabilityInvocation,
    WorkflowCapabilityResult,
    WorkflowCapabilitySpec,
)
from aithru_agent.capabilities.web import WebToolInvocation, WebToolProvider, WebToolResult
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    ResearchLocalTool,
    TodoLocalTool,
    WorkspaceLocalTool,
)
from aithru_agent.domain import (
    AgentExternalRunRef,
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


class FailingLocalTool:
    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="local.fail",
                kind="local_tool",
                description="Always fail for non-recoverable failure testing.",
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
        return AgentToolCallResult(
            status="failed",
            error={"message": "local tool failed"},
            redaction="none",
        )


class FailingWebExecutor:
    async def execute(self, invocation: WebToolInvocation) -> WebToolResult:
        return WebToolResult(
            status="failed",
            error={"message": f"{invocation.action} provider unavailable"},
            redaction="partial",
        )


class FailingWebNamedLocalTool:
    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="web.search",
                kind="local_tool",
                description="A web-named local tool without recoverable failure policy.",
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
        return AgentToolCallResult(
            status="failed",
            error={"message": "web-named local tool failed"},
            redaction="none",
        )


class FakeWorkflowCapabilityProvider:
    def list_capabilities(self) -> list[WorkflowCapabilitySpec]:
        return [
            WorkflowCapabilitySpec(
                key="report_review",
                tool_name="workflow.report_review",
                description="Run report review in Workbench.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_level="write",
                required_scopes=["workflow.capability.report_review.invoke"],
                approval_policy="never",
            )
        ]

    async def invoke(
        self,
        invocation: WorkflowCapabilityInvocation,
    ) -> WorkflowCapabilityResult:
        return WorkflowCapabilityResult(
            status="completed",
            output={"review_status": "accepted"},
            redaction="none",
            external_run=AgentExternalRunRef(
                kind="workflow_capability",
                capability_key=invocation.capability_key,
                capability_run_id="caprun_bridge_1",
                status="completed",
                correlation_id=invocation.correlation_id,
            ),
        )


class WaitingWorkflowCapabilityProvider:
    def list_capabilities(self) -> list[WorkflowCapabilitySpec]:
        return [
            WorkflowCapabilitySpec(
                key="report_review",
                tool_name="workflow.report_review",
                description="Run report review in Workbench.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_level="write",
                required_scopes=["workflow.capability.report_review.invoke"],
                approval_policy="never",
            )
        ]

    async def invoke(
        self,
        invocation: WorkflowCapabilityInvocation,
    ) -> WorkflowCapabilityResult:
        return WorkflowCapabilityResult(
            status="waiting_approval",
            output={"message": "Workflow approval required."},
            redaction="none",
            external_run=AgentExternalRunRef(
                kind="workflow_capability",
                capability_key=invocation.capability_key,
                capability_run_id="caprun_waiting_1",
                status="waiting_approval",
                correlation_id=invocation.correlation_id,
                approval_id="capapproval_1",
            ),
        )


class RunningWorkflowCapabilityProvider:
    def list_capabilities(self) -> list[WorkflowCapabilitySpec]:
        return [
            WorkflowCapabilitySpec(
                key="report_review",
                tool_name="workflow.report_review",
                description="Run report review in Workbench.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_level="write",
                required_scopes=["workflow.capability.report_review.invoke"],
                approval_policy="never",
            )
        ]

    async def invoke(
        self,
        invocation: WorkflowCapabilityInvocation,
    ) -> WorkflowCapabilityResult:
        return WorkflowCapabilityResult(
            status="running",
            output={"message": "Workflow capability run started."},
            redaction="none",
            external_run=AgentExternalRunRef(
                kind="workflow_capability",
                capability_key=invocation.capability_key,
                capability_run_id="caprun_running_1",
                status="running",
                correlation_id=invocation.correlation_id,
            ),
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
async def test_pydantic_tool_bridge_emits_external_run_events_for_workflow_capability() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Run workflow capability",
        workspace_id=workspace.id,
    )
    context = AgentRunContext(
        run_id=run.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    bridge = PydanticAIToolBridge(
        deps=PydanticAgentDeps(
            run=run,
            run_context=context,
            event_writer=writer,
            capability_router=AithruCapabilityRouter(
                adapters=[WorkflowCapabilityAdapter(FakeWorkflowCapabilityProvider())],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    result = await bridge.call_tool(
        ToolContext("tc_workflow"),
        tool_name="workflow.report_review",
        tool_input={"artifact_id": "artifact_1"},
    )
    events = await event_store.list_by_run(run.id)
    completed = next(event for event in events if event.type == "tool.completed")

    assert result == {"review_status": "accepted"}
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "external_run.created",
        "external_run.completed",
        "tool.completed",
    ]
    assert events[2].source.kind == "workflow"
    assert events[2].payload == {
        "kind": "workflow_capability",
        "tool_call_id": "tc_workflow",
        "tool_name": "workflow.report_review",
        "capability_key": "report_review",
        "capability_run_id": "caprun_bridge_1",
        "status": "completed",
        "correlation_id": f"{run.id}:tc_workflow",
        "approval_id": None,
    }
    assert completed.payload["external_run"] == {
        "kind": "workflow_capability",
        "capability_key": "report_review",
        "capability_run_id": "caprun_bridge_1",
        "status": "completed",
        "correlation_id": f"{run.id}:tc_workflow",
        "approval_id": None,
    }


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_pauses_for_workflow_owned_approval() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Run workflow capability that needs external approval",
        workspace_id=workspace.id,
    )
    running = await store.claim_run(run.id)
    assert running is not None
    context = AgentRunContext(
        run_id=running.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    bridge = PydanticAIToolBridge(
        deps=PydanticAgentDeps(
            run=running,
            run_context=context,
            event_writer=writer,
            capability_router=AithruCapabilityRouter(
                adapters=[WorkflowCapabilityAdapter(WaitingWorkflowCapabilityProvider())],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    with pytest.raises(RunPausedForExternalApproval) as exc_info:
        await bridge.call_tool(
            ToolContext("tc_waiting_workflow"),
            tool_name="workflow.report_review",
            tool_input={"artifact_id": "artifact_1"},
        )
    paused = await store.get_run(running.id)
    events = await event_store.list_by_run(running.id)

    assert exc_info.value.approval_id == "capapproval_1"
    assert exc_info.value.capability_run_id == "caprun_waiting_1"
    assert paused.status == AgentRunStatus.WAITING_APPROVAL
    assert paused.current_approval_id is None
    assert paused.current_external_approval.model_dump(mode="json") == {
        "kind": "workflow_capability",
        "capability_key": "report_review",
        "capability_run_id": "caprun_waiting_1",
        "approval_id": "capapproval_1",
        "tool_call_id": "tc_waiting_workflow",
        "tool_name": "workflow.report_review",
        "correlation_id": f"{running.id}:tc_waiting_workflow",
        "status": "pending",
    }
    assert await store.list_approvals() == []
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "external_run.created",
        "external_approval.requested",
        "tool.completed",
        "run.paused",
    ]
    assert "run.failed" not in [event.type for event in events]
    assert events[-1].payload["current_external_approval"]["approval_id"] == "capapproval_1"


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_pauses_for_running_workflow_capability_run() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Run asynchronous workflow capability",
        workspace_id=workspace.id,
    )
    running = await store.claim_run(run.id)
    assert running is not None
    context = AgentRunContext(
        run_id=running.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    bridge = PydanticAIToolBridge(
        deps=PydanticAgentDeps(
            run=running,
            run_context=context,
            event_writer=writer,
            capability_router=AithruCapabilityRouter(
                adapters=[WorkflowCapabilityAdapter(RunningWorkflowCapabilityProvider())],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    with pytest.raises(RunPausedForExternalRun) as exc_info:
        await bridge.call_tool(
            ToolContext("tc_running_workflow"),
            tool_name="workflow.report_review",
            tool_input={"artifact_id": "artifact_1"},
        )
    paused = await store.get_run(running.id)
    events = await event_store.list_by_run(running.id)

    assert exc_info.value.capability_run_id == "caprun_running_1"
    assert paused.status == AgentRunStatus.WAITING_EXTERNAL_RUN
    assert paused.current_approval_id is None
    assert paused.current_external_approval is None
    assert paused.current_external_run.model_dump(mode="json") == {
        "kind": "workflow_capability",
        "capability_key": "report_review",
        "capability_run_id": "caprun_running_1",
        "tool_call_id": "tc_running_workflow",
        "tool_name": "workflow.report_review",
        "correlation_id": f"{running.id}:tc_running_workflow",
        "status": "running",
    }
    assert await store.list_approvals() == []
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "external_run.created",
        "tool.completed",
        "run.paused",
    ]
    assert events[3].payload["status"] == "running"
    assert events[3].payload["audit"]["outcome"] == "running"
    assert events[4].payload["current_external_run"]["capability_run_id"] == "caprun_running_1"
    assert "run.failed" not in [event.type for event in events]


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_persists_capability_audit_in_tool_events() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="List files",
        workspace_id=workspace.id,
    )
    context = AgentRunContext(
        run_id=run.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.workspace.read"],
    )
    bridge = PydanticAIToolBridge(
        deps=PydanticAgentDeps(
            run=run,
            run_context=context,
            event_writer=writer,
            capability_router=AithruCapabilityRouter(
                adapters=[WorkspaceLocalTool(store)],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    await bridge.call_tool(
        ToolContext("tc_audit"),
        tool_name="workspace.list_files",
        tool_input={},
    )
    events = await event_store.list_by_run(run.id)
    completed = next(event for event in events if event.type == "tool.completed")

    assert completed.redaction == "none"
    assert completed.payload["authorization_decision"]["status"] == "allowed"
    assert completed.payload["authorization_decision"]["required_scopes"] == ["agent.workspace.read"]
    assert completed.payload["audit"]["action"] == "tool.execute"
    assert completed.payload["audit"]["outcome"] == "completed"
    assert completed.payload["audit"]["run_id"] == run.id
    assert completed.payload["audit"]["tool_name"] == "workspace.list_files"
    assert "authorization" not in completed.payload["audit"]
    assert completed.payload["audit"]["authorization_decision"]["actor"]["user_id"] == "user_1"


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
async def test_pydantic_tool_bridge_emits_artifact_event_for_research_report() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Create research report",
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
                adapters=[ResearchLocalTool(store)],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    result = await bridge.call_tool(
        ToolContext("tc_research"),
        tool_name="research.create_report",
        tool_input={
            "title": "Aithru research",
            "query": "aithru",
            "sources": [
                {
                    "title": "Aithru Agent",
                    "url": "https://example.com/aithru",
                    "snippet": "Harness backend.",
                }
            ],
        },
    )
    events = await event_store.list_by_run(run.id)

    assert result["artifact"]["type"] == "report"
    assert result["artifact"]["metadata"]["evidence_count"] == 1
    assert result["artifact"]["metadata"]["source_input_count"] == 1
    assert result["artifact"]["metadata"]["duplicate_source_count"] == 0
    assert result["artifact"]["metadata"]["quality_summary"] == {
        "high": 0,
        "medium": 1,
        "low": 0,
    }
    assert result["report"]["evidence"] == [
        {
            "citation_number": 1,
            "title": "Aithru Agent",
            "url": "https://example.com/aithru",
            "snippet": "Harness backend.",
            "excerpt": None,
            "source": None,
            "published_at": None,
            "section_id": None,
            "quality": {
                "label": "medium",
                "score": 60,
                "reasons": ["valid_http_source", "has_search_snippet"],
            },
        }
    ]
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "artifact.created",
        "tool.completed",
    ]
    assert events[2].payload["id"] == result["artifact"]["id"]


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_creates_degraded_research_report_artifact() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Create degraded research report",
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
                adapters=[ResearchLocalTool(store)],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    result = await bridge.call_tool(
        ToolContext("tc_degraded_research"),
        tool_name="research.create_report",
        tool_input={
            "title": "Aithru degraded research",
            "query": "aithru",
            "sources": [],
            "limitations": [
                {
                    "code": "search_no_results",
                    "severity": "warning",
                    "message": "Controlled search returned no results.",
                }
            ],
        },
    )
    events = await event_store.list_by_run(run.id)

    assert result["report"]["status"] == "insufficient_evidence"
    assert result["artifact"]["metadata"]["report_status"] == "insufficient_evidence"
    assert result["artifact"]["metadata"]["source_count"] == 0
    assert result["artifact"]["metadata"]["limitation_count"] == 1
    assert "Controlled search returned no results." in result["artifact"]["content"]
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "artifact.created",
        "tool.completed",
    ]


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_emits_todo_events_for_research_plan() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Plan research",
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
                adapters=[ResearchLocalTool(store)],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    result = await bridge.call_tool(
        ToolContext("tc_research_plan"),
        tool_name="research.create_plan",
        tool_input={"query": "aithru deerflow parity"},
    )
    events = await event_store.list_by_run(run.id)

    assert [todo["title"] for todo in result["todos"]] == [
        "Search sources",
        "Fetch and review sources",
        "Synthesize findings",
        "Create research report",
    ]
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "todo.created",
        "todo.created",
        "todo.created",
        "todo.created",
        "tool.completed",
    ]


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "failed_ref", "blocked_title", "message"),
    [
        (
            "web.search",
            {"query": "aithru deerflow parity"},
            {"query": "aithru deerflow parity"},
            "Search sources",
            "search provider unavailable",
        ),
        (
            "web.fetch",
            {"url": "https://example.com/aithru"},
            {"url": "https://example.com/aithru"},
            "Fetch and review sources",
            "fetch provider unavailable",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pydantic_tool_bridge_emits_web_failure_event_and_blocks_research_todo(
    tool_name: str,
    tool_input: dict[str, object],
    failed_ref: dict[str, object],
    blocked_title: str,
    message: str,
) -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Research with failing web tools",
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
                adapters=[
                    ResearchLocalTool(store),
                    ExternalToolAdapter(WebToolProvider(executor=FailingWebExecutor())),
                ],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )
    await bridge.call_tool(
        ToolContext("tc_research_plan"),
        tool_name="research.create_plan",
        tool_input={"query": "aithru deerflow parity"},
    )

    result = await bridge.call_tool(
        ToolContext("tc_web"),
        tool_name=tool_name,
        tool_input=tool_input,
    )
    events = await event_store.list_by_run(run.id)
    todos = await store.list_todos(run.id)
    failed_event = next(event for event in events if event.type == f"{tool_name}.failed")

    assert result == {
        "status": "failed",
        "recoverable": True,
        "tool_name": tool_name,
        **failed_ref,
        "error": {"message": message},
        "limitation": {
            "code": "web_search_failed" if tool_name == "web.search" else "web_fetch_failed",
            "severity": "warning",
            "message": (
                "Controlled web search failed for `aithru deerflow parity`: "
                "search provider unavailable."
                if tool_name == "web.search"
                else "Controlled web fetch failed: fetch provider unavailable."
            ),
            "source_url": None if tool_name == "web.search" else "https://example.com/aithru",
        },
    }
    assert [event.type for event in events][-5:] == [
        "tool.proposed",
        "tool.started",
        f"{tool_name}.failed",
        "todo.updated",
        "tool.failed",
    ]
    assert failed_event.source.kind == "web"
    assert failed_event.payload == {
        "tool_call_id": "tc_web",
        **failed_ref,
        "error": {"message": message},
        "limitation": {
            "code": "web_search_failed" if tool_name == "web.search" else "web_fetch_failed",
            "severity": "warning",
            "message": (
                "Controlled web search failed for `aithru deerflow parity`: "
                "search provider unavailable."
                if tool_name == "web.search"
                else "Controlled web fetch failed: fetch provider unavailable."
            ),
            "source_url": None if tool_name == "web.search" else "https://example.com/aithru",
        },
    }
    assert {todo.title: todo.status.value for todo in todos} == {
        "Search sources": "blocked" if blocked_title == "Search sources" else "pending",
        "Fetch and review sources": "blocked"
        if blocked_title == "Fetch and review sources"
        else "pending",
        "Synthesize findings": "pending",
        "Create research report": "pending",
    }


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_still_raises_for_non_recoverable_tool_failures() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Use failing local tool",
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
                adapters=[FailingLocalTool()],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    with pytest.raises(AgentError) as exc_info:
        await bridge.call_tool(
            ToolContext("tc_local_fail"),
            tool_name="local.fail",
            tool_input={},
        )
    events = await event_store.list_by_run(run.id)

    assert exc_info.value.code == "TOOL_FAILED"
    assert exc_info.value.message == "local tool failed"
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "tool.failed",
    ]


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_uses_descriptor_failure_policy_for_recovery() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Use web-named non-recoverable tool",
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
                adapters=[FailingWebNamedLocalTool()],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    with pytest.raises(AgentError) as exc_info:
        await bridge.call_tool(
            ToolContext("tc_web_named_fail"),
            tool_name="web.search",
            tool_input={"query": "aithru"},
        )

    assert exc_info.value.code == "TOOL_FAILED"
    assert exc_info.value.message == "web-named local tool failed"


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
    assert [event.type for event in events][-12:] == [
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
        "memory.candidate.created",
        "run.completed",
    ]
