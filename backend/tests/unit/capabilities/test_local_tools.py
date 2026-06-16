import pytest

from aithru_agent.capabilities import (
    AgentRunContext,
    AithruCapabilityRouter,
    ToolPolicy,
)
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    TodoLocalTool,
    WorkspaceLocalTool,
)
from aithru_agent.domain import AgentToolCallRequest
from aithru_agent.persistence.memory.store import InMemoryAgentStore


async def make_context(store: InMemoryAgentStore) -> AgentRunContext:
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Do work",
        workspace_id=workspace.id,
    )
    return AgentRunContext(
        run_id=run.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=[
            "agent.workspace.read",
            "agent.workspace.write",
            "agent.todo.write",
            "agent.artifact.write",
        ],
    )


def make_router(store: InMemoryAgentStore, policy: ToolPolicy | None = None) -> AithruCapabilityRouter:
    return AithruCapabilityRouter(
        adapters=[
            WorkspaceLocalTool(store),
            TodoLocalTool(store),
            ArtifactLocalTool(store),
        ],
        policy=policy or ToolPolicy(require_approval_for_risk=[]),
    )


@pytest.mark.asyncio
async def test_router_lists_local_tools_with_risk_and_scopes() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)

    tools = await router.list_tools(context)
    by_name = {tool.name: tool for tool in tools}

    assert by_name["workspace.read_file"].risk_level == "read"
    assert by_name["workspace.write_file"].risk_level == "write"
    assert by_name["todo.create"].required_scopes == ["agent.todo.write"]
    assert by_name["artifact.create"].required_scopes == ["agent.artifact.write"]


@pytest.mark.asyncio
async def test_workspace_tool_calls_execute_through_router() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)

    write = AgentToolCallRequest(
        id="toolcall_1",
        tool_name="workspace.write_file",
        input={"path": "/notes.md", "content": "# Notes", "media_type": "text/markdown"},
        requested_by="model",
    )
    prepared = await router.prepare_tool_call(write, context)
    result = await router.execute_tool_call(write, context)
    read = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_2",
            tool_name="workspace.read_file",
            input={"path": "/notes.md"},
            requested_by="model",
        ),
        context,
    )

    assert prepared.status == "ready"
    assert result.status == "completed"
    assert result.output["path"] == "/notes.md"
    assert read.output == {"path": "/notes.md", "content": "# Notes", "media_type": "text/markdown"}


@pytest.mark.asyncio
async def test_write_tool_waits_for_approval_when_policy_requires_write_approval() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store, ToolPolicy(require_approval_for_risk=["write"]))

    request = AgentToolCallRequest(
        id="toolcall_1",
        tool_name="workspace.write_file",
        input={"path": "/notes.md", "content": "# Notes"},
        requested_by="model",
    )

    prepared = await router.prepare_tool_call(request, context)
    denied_execution = await router.execute_tool_call(request, context)
    approved_execution = await router.execute_tool_call(
        request.model_copy(update={"already_approved": True, "requested_by": "harness"}),
        context,
    )

    assert prepared.status == "waiting_approval"
    assert denied_execution.status == "waiting_approval"
    assert approved_execution.status == "completed"


@pytest.mark.asyncio
async def test_todo_and_artifact_tools_return_normalized_results() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)

    todo_result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="todo.create",
            input={"title": "Read files", "status": "running"},
            requested_by="model",
        ),
        context,
    )
    artifact_result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_2",
            tool_name="artifact.create",
            input={
                "type": "report",
                "name": "Report",
                "uri": "/reports/report.md",
                "content": {"summary": "done"},
            },
            requested_by="model",
        ),
        context,
    )

    assert todo_result.status == "completed"
    assert todo_result.output["title"] == "Read files"
    assert todo_result.output["status"] == "running"
    assert artifact_result.status == "completed"
    assert artifact_result.output["type"] == "report"
    assert artifact_result.output["uri"] == "/reports/report.md"
