import pytest

from aithru_agent.capabilities import AgentRunContext, ToolPolicy
from aithru_agent.capabilities.router import AithruCapabilityRouter
from aithru_agent.capabilities.local_tools import SandboxLocalTool
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus, AgentSandboxPolicy, AgentToolCallRequest
from aithru_agent.sandbox import SandboxExecutionRequest, SandboxExecutionResult
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from tests.utils.step_runtime import Step, StepAgentRuntime
from aithru_agent.trace import project_trace_spans


class FakeSandboxProvider:
    def __init__(self) -> None:
        self.requests: list[SandboxExecutionRequest] = []

    async def run_python(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        self.requests.append(request)
        return SandboxExecutionResult(
            status="completed",
            stdout="fake stdout\n",
            stderr="",
            result={"ok": True},
        )


@pytest.mark.asyncio
async def test_sandbox_read_file_requires_workspace_read_scope_through_router() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute"],
    )

    tools = await router.list_tools(context)
    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_read",
            tool_name="sandbox.read_file",
            input={"path": "/reports/summary.md"},
            requested_by="model",
        ),
        context,
    )

    assert "sandbox.read_file" not in [tool.name for tool in tools]
    assert result.status == "denied"
    assert result.authorization.missing_scopes == ["agent.workspace.read"]


@pytest.mark.asyncio
async def test_sandbox_read_file_returns_text_metadata_and_respects_max_bytes() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="abcdef",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_read",
            tool_name="sandbox.read_file",
            input={"path": "/reports/summary.md", "max_bytes": 4},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output == {
        "path": "/reports/summary.md",
        "content": "abcd",
        "media_type": "text/markdown",
        "content_encoding": "utf-8",
        "size": 6,
        "returned_bytes": 4,
        "truncated": True,
    }
    assert result.audit.outcome == "completed"


@pytest.mark.asyncio
async def test_sandbox_read_file_denies_paths_outside_workspace_policy() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/private/summary.md",
        content="secret",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_read",
            tool_name="sandbox.read_file",
            input={"path": "/private/summary.md"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "denied"
    assert result.error["message"] == "Path is outside allowed workspace paths: /private/summary.md"
    assert result.audit.outcome == "denied"


@pytest.mark.asyncio
async def test_sandbox_read_file_returns_binary_content_as_base64() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/blob.bin",
        content=b"\x00\xffabc",
        media_type="application/octet-stream",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_read",
            tool_name="sandbox.read_file",
            input={"path": "/reports/blob.bin", "max_bytes": 3},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output["content"] == "AP9h"
    assert result.output["content_encoding"] == "base64"
    assert result.output["size"] == 5
    assert result.output["returned_bytes"] == 3
    assert result.output["truncated"] is True


@pytest.mark.asyncio
async def test_sandbox_list_files_requires_workspace_read_scope_through_router() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute"],
    )

    tools = await router.list_tools(context)
    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_list",
            tool_name="sandbox.list_files",
            input={},
            requested_by="model",
        ),
        context,
    )

    assert "sandbox.list_files" not in [tool.name for tool in tools]
    assert result.status == "denied"
    assert result.authorization.missing_scopes == ["agent.workspace.read"]


@pytest.mark.asyncio
async def test_sandbox_list_files_returns_allowed_metadata_without_content() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="# Summary",
        media_type="text/markdown",
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/data.json",
        content='{"ok": true}',
        media_type="application/json",
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/private/secret.md",
        content="secret",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_list",
            tool_name="sandbox.list_files",
            input={"prefix": "/reports", "limit": 10},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output["workspace_id"] == workspace.id
    assert result.output["prefix"] == "/reports"
    assert result.output["count"] == 2
    assert result.output["total_count"] == 2
    assert result.output["truncated"] is False
    assert [file["path"] for file in result.output["files"]] == [
        "/reports/data.json",
        "/reports/summary.md",
    ]
    assert "content" not in result.output["files"][0]
    assert result.audit.outcome == "completed"


@pytest.mark.asyncio
async def test_sandbox_list_files_applies_limit_after_allowed_path_filtering() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(workspace_id=workspace.id, path="/reports/a.md", content="a")
    await store.write_workspace_file(workspace_id=workspace.id, path="/reports/b.md", content="b")
    await store.write_workspace_file(workspace_id=workspace.id, path="/private/c.md", content="c")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_list",
            tool_name="sandbox.list_files",
            input={"limit": 1},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert [file["path"] for file in result.output["files"]] == ["/reports/a.md"]
    assert result.output["count"] == 1
    assert result.output["total_count"] == 2
    assert result.output["truncated"] is True


@pytest.mark.asyncio
async def test_sandbox_list_files_denies_prefix_outside_workspace_policy() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_list",
            tool_name="sandbox.list_files",
            input={"prefix": "/private"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "denied"
    assert result.error["message"] == "Path is outside allowed workspace paths: /private"


@pytest.mark.asyncio
async def test_sandbox_list_files_fails_without_workspace_store() -> None:
    event_store = InMemoryAgentEventStore()
    tool = SandboxLocalTool(AgentEventWriter(event_store))
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_list",
            tool_name="sandbox.list_files",
            input={},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "failed"
    assert result.error["message"] == "Sandbox file listing requires a workspace store"


@pytest.mark.asyncio
async def test_sandbox_write_file_requires_workspace_write_scope_and_write_approval() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)],
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    missing_write_context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute"],
    )
    write_context = missing_write_context.model_copy(
        update={"scopes": ["agent.sandbox.execute", "agent.workspace.write"]}
    )
    request = AgentToolCallRequest(
        id="toolcall_write",
        tool_name="sandbox.write_file",
        input={"path": "/reports/summary.md", "content": "# Summary"},
        requested_by="model",
    )

    missing_scope = await router.execute_tool_call(request, missing_write_context)
    waiting = await router.execute_tool_call(request, write_context)

    assert missing_scope.status == "denied"
    assert missing_scope.authorization.missing_scopes == ["agent.workspace.write"]
    assert waiting.status == "waiting_approval"


@pytest.mark.asyncio
async def test_sandbox_write_file_persists_workspace_file_and_emits_event() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_write",
            tool_name="sandbox.write_file",
            input={
                "path": "/reports/summary.md",
                "content": "# Summary",
                "media_type": "text/markdown",
            },
            requested_by="model",
        ),
        context,
    )
    written = await store.read_workspace_file(workspace.id, "/reports/summary.md")
    events = await event_store.list_by_run("run_1")

    assert result.status == "completed"
    assert result.output["source"] == "sandbox.write_file"
    assert result.output["workspace_id"] == workspace.id
    assert result.output["path"] == "/reports/summary.md"
    assert result.output["file"]["path"] == "/reports/summary.md"
    assert result.output["size"] == len("# Summary".encode("utf-8"))
    assert result.output["media_type"] == "text/markdown"
    assert result.output["overwritten"] is False
    assert written.content == "# Summary"
    workspace_event = next(event for event in events if event.type == "workspace.file.created")
    assert workspace_event.payload["source"] == "sandbox.write_file"
    assert workspace_event.payload["tool_call_id"] == "toolcall_write"
    assert workspace_event.payload["path"] == "/reports/summary.md"


@pytest.mark.asyncio
async def test_sandbox_write_file_reports_overwrites() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="old",
        media_type="text/plain",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_write",
            tool_name="sandbox.write_file",
            input={"path": "/reports/summary.md", "content": "new"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output["overwritten"] is True
    assert result.output["file"]["file_version"] == 2


@pytest.mark.asyncio
async def test_sandbox_write_file_denies_paths_outside_workspace_policy() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_write",
            tool_name="sandbox.write_file",
            input={"path": "/private/summary.md", "content": "secret"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "denied"
    assert result.error["message"] == "Path is outside allowed workspace paths: /private/summary.md"
    assert (await store.list_workspace_files(workspace.id)) == []


@pytest.mark.asyncio
async def test_sandbox_delete_file_requires_workspace_write_scope_and_write_approval() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="# Summary",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)],
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    missing_write_context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute"],
    )
    delete_context = missing_write_context.model_copy(
        update={"scopes": ["agent.sandbox.execute", "agent.workspace.write"]}
    )
    request = AgentToolCallRequest(
        id="toolcall_delete",
        tool_name="sandbox.delete_file",
        input={"path": "/reports/summary.md"},
        requested_by="model",
    )

    missing_scope = await router.execute_tool_call(request, missing_write_context)
    waiting = await router.execute_tool_call(request, delete_context)

    assert missing_scope.status == "denied"
    assert missing_scope.authorization.missing_scopes == ["agent.workspace.write"]
    assert waiting.status == "waiting_approval"


@pytest.mark.asyncio
async def test_sandbox_delete_file_removes_workspace_file_and_emits_event() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="# Summary",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_delete",
            tool_name="sandbox.delete_file",
            input={"path": "/reports/summary.md"},
            requested_by="model",
        ),
        context,
    )
    events = await event_store.list_by_run("run_1")
    versions = await store.list_workspace_file_versions(
        workspace_id=workspace.id,
        path="/reports/summary.md",
    )

    assert result.status == "completed"
    assert result.output["workspace_id"] == workspace.id
    assert result.output["path"] == "/reports/summary.md"
    assert result.output["deleted"] is True
    assert result.output["version_before"] == 1
    assert result.output["deleted_version"] == 2
    assert result.output["file_version_before"] == 1
    assert result.output["deleted_file_version"] == 2
    assert [version.operation for version in versions] == ["write", "delete"]
    assert await store.list_workspace_files(workspace.id) == []
    workspace_event = next(event for event in events if event.type == "workspace.file.deleted")
    assert workspace_event.payload["source"] == "sandbox.delete_file"
    assert workspace_event.payload["tool_call_id"] == "toolcall_delete"
    assert workspace_event.payload["path"] == "/reports/summary.md"


@pytest.mark.asyncio
async def test_sandbox_delete_file_denies_paths_outside_workspace_policy() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/private/summary.md",
        content="secret",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_delete",
            tool_name="sandbox.delete_file",
            input={"path": "/private/summary.md"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "denied"
    assert result.error["message"] == "Path is outside allowed workspace paths: /private/summary.md"
    assert [file.path for file in await store.list_workspace_files(workspace.id)] == [
        "/private/summary.md"
    ]


@pytest.mark.asyncio
async def test_sandbox_delete_file_fails_without_workspace_store() -> None:
    event_store = InMemoryAgentEventStore()
    tool = SandboxLocalTool(AgentEventWriter(event_store))
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_delete",
            tool_name="sandbox.delete_file",
            input={"path": "/reports/summary.md"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "failed"
    assert result.error["message"] == "Sandbox file deletion requires a workspace store"


@pytest.mark.asyncio
async def test_sandbox_patch_file_requires_workspace_write_scope_and_write_approval() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)],
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    missing_write_context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute"],
    )
    write_context = missing_write_context.model_copy(
        update={"scopes": ["agent.sandbox.execute", "agent.workspace.write"]}
    )
    request = AgentToolCallRequest(
        id="toolcall_patch",
        tool_name="sandbox.patch_file",
        input={
            "path": "/reports/summary.md",
            "edits": [{"old_text": "draft", "new_text": "done"}],
        },
        requested_by="model",
    )

    missing_scope = await router.execute_tool_call(request, missing_write_context)
    waiting = await router.execute_tool_call(request, write_context)

    assert missing_scope.status == "denied"
    assert missing_scope.authorization.missing_scopes == ["agent.workspace.write"]
    assert waiting.status == "waiting_approval"


@pytest.mark.asyncio
async def test_sandbox_patch_file_applies_structured_edits_and_emits_event() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/report.md",
        content="# Draft\nOld title\nNeeds work.\nOld title\n",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_patch",
            tool_name="sandbox.patch_file",
            input={
                "path": "/reports/report.md",
                "edits": [
                    {
                        "old_text": "Old title",
                        "new_text": "Reviewed title",
                        "replace_all": True,
                        "expected_replacements": 2,
                    },
                    {"old_text": "Needs work.", "new_text": "Ready for review."},
                ],
            },
            requested_by="model",
        ),
        context,
    )
    patched = await store.read_workspace_file(workspace.id, "/reports/report.md")
    events = await event_store.list_by_run("run_1")

    assert result.status == "completed"
    assert result.output["workspace_id"] == workspace.id
    assert result.output["path"] == "/reports/report.md"
    assert result.output["replacement_count"] == 3
    assert result.output["version_before"] == 1
    assert result.output["version_after"] == 2
    assert result.output["file_version_before"] == 1
    assert result.output["file_version_after"] == 2
    assert patched.content == "# Draft\nReviewed title\nReady for review.\nReviewed title\n"
    assert patched.media_type == "text/markdown"
    workspace_event = next(event for event in events if event.type == "workspace.file.created")
    assert workspace_event.payload["source"] == "sandbox.patch_file"
    assert workspace_event.payload["tool_call_id"] == "toolcall_patch"
    assert workspace_event.payload["path"] == "/reports/report.md"


@pytest.mark.asyncio
async def test_sandbox_patch_file_denies_paths_outside_workspace_policy() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/private/summary.md",
        content="draft",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_patch",
            tool_name="sandbox.patch_file",
            input={
                "path": "/private/summary.md",
                "edits": [{"old_text": "draft", "new_text": "done"}],
            },
            requested_by="model",
        ),
        context,
    )
    unchanged = await store.read_workspace_file(workspace.id, "/private/summary.md")

    assert result.status == "denied"
    assert result.error["message"] == "Path is outside allowed workspace paths: /private/summary.md"
    assert unchanged.content == "draft"


@pytest.mark.asyncio
async def test_sandbox_patch_file_rejects_binary_workspace_files() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/blob.bin",
        content=b"draft",
        media_type="application/octet-stream",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_patch",
            tool_name="sandbox.patch_file",
            input={
                "path": "/reports/blob.bin",
                "edits": [{"old_text": "draft", "new_text": "done"}],
            },
            requested_by="model",
        ),
        context,
    )

    assert result.status == "denied"
    assert result.error["message"] == "sandbox.patch_file only supports text files"


@pytest.mark.asyncio
async def test_sandbox_diff_requires_workspace_read_scope_through_router() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute"],
    )

    tools = await router.list_tools(context)
    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_diff",
            tool_name="sandbox.diff",
            input={},
            requested_by="model",
        ),
        context,
    )

    assert "sandbox.diff" not in [tool.name for tool in tools]
    assert result.status == "denied"
    assert result.authorization.missing_scopes == ["agent.workspace.read"]


@pytest.mark.asyncio
async def test_sandbox_diff_returns_versioned_workspace_changes() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="old",
        media_type="text/markdown",
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/notes.md",
        content="notes",
        media_type="text/markdown",
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="new",
        media_type="text/markdown",
    )
    await store.delete_workspace_file(workspace.id, "/reports/notes.md")
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_diff",
            tool_name="sandbox.diff",
            input={"base_version": 2, "target_version": 4},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output["workspace_id"] == workspace.id
    assert result.output["base_version"] == 2
    assert result.output["target_version"] == 4
    assert [(change["path"], change["operation"]) for change in result.output["changes"]] == [
        ("/reports/notes.md", "deleted"),
        ("/reports/summary.md", "modified"),
    ]
    assert result.output["added_count"] == 0
    assert result.output["modified_count"] == 1
    assert result.output["deleted_count"] == 1
    assert result.audit.outcome == "completed"


@pytest.mark.asyncio
async def test_sandbox_diff_filters_changes_by_workspace_allowed_paths() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="old",
        media_type="text/markdown",
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/private/secret.md",
        content="secret",
        media_type="text/markdown",
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="new",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_diff",
            tool_name="sandbox.diff",
            input={"base_version": 0, "target_version": 3},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert [(change["path"], change["operation"]) for change in result.output["changes"]] == [
        ("/reports/summary.md", "added")
    ]
    assert result.output["added_count"] == 1
    assert result.output["modified_count"] == 0
    assert result.output["deleted_count"] == 0


@pytest.mark.asyncio
async def test_sandbox_diff_fails_without_workspace_store() -> None:
    event_store = InMemoryAgentEventStore()
    tool = SandboxLocalTool(AgentEventWriter(event_store))
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_diff",
            tool_name="sandbox.diff",
            input={},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "failed"
    assert result.error["message"] == "Sandbox workspace diffs require a workspace store"


@pytest.mark.asyncio
async def test_sandbox_promote_file_requires_artifact_scope_and_write_approval() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="# Summary",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)],
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    missing_artifact_context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read"],
    )
    promote_context = missing_artifact_context.model_copy(
        update={
            "scopes": [
                "agent.sandbox.execute",
                "agent.workspace.read",
                "agent.artifact.write",
            ]
        }
    )
    request = AgentToolCallRequest(
        id="toolcall_promote",
        tool_name="sandbox.promote_file",
        input={"path": "/reports/summary.md", "name": "Sandbox Summary", "type": "report"},
        requested_by="model",
    )

    missing_scope = await router.execute_tool_call(request, missing_artifact_context)
    waiting = await router.execute_tool_call(request, promote_context)

    assert missing_scope.status == "denied"
    assert missing_scope.authorization.missing_scopes == ["agent.artifact.write"]
    assert waiting.status == "waiting_approval"


@pytest.mark.asyncio
async def test_sandbox_promote_file_creates_managed_artifact_and_event() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/summary.md",
        content="# Summary",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read", "agent.artifact.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_promote",
            tool_name="sandbox.promote_file",
            input={
                "path": "/reports/summary.md",
                "name": "Sandbox Summary",
                "type": "report",
                "metadata": {"kind": "sandbox_output"},
            },
            requested_by="model",
        ),
        context,
    )
    artifacts = await store.list_artifacts(run_id="run_1")
    events = await event_store.list_by_run("run_1")

    assert result.status == "completed"
    assert result.output["workspace_id"] == workspace.id
    assert result.output["path"] == "/reports/summary.md"
    assert result.output["artifact"]["name"] == "Sandbox Summary"
    assert result.output["artifact"]["type"] == "report"
    assert result.output["artifact"]["uri"] == "/reports/summary.md"
    assert result.output["artifact"]["metadata"]["source"] == "workspace_file"
    assert result.output["artifact"]["metadata"]["kind"] == "sandbox_output"
    assert result.output["artifact"]["metadata"]["workspace_file"]["path"] == "/reports/summary.md"
    assert result.output["artifact"]["metadata"]["sandbox"]["source"] == "sandbox.promote_file"
    assert result.output["artifact"]["metadata"]["sandbox"]["tool_call_id"] == "toolcall_promote"
    assert [artifact.name for artifact in artifacts] == ["Sandbox Summary"]
    artifact_event = next(event for event in events if event.type == "artifact.created")
    assert artifact_event.payload["source"] == "sandbox.promote_file"
    assert artifact_event.payload["tool_call_id"] == "toolcall_promote"
    assert artifact_event.payload["artifact_id"] == result.output["artifact"]["id"]


@pytest.mark.asyncio
async def test_sandbox_promote_file_denies_paths_outside_workspace_policy() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/private/summary.md",
        content="secret",
        media_type="text/markdown",
    )
    event_store = InMemoryAgentEventStore()
    router = AithruCapabilityRouter(
        adapters=[SandboxLocalTool(AgentEventWriter(event_store), store=store)]
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.read", "agent.artifact.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_promote",
            tool_name="sandbox.promote_file",
            input={"path": "/private/summary.md", "name": "Secret Summary"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "denied"
    assert result.error["message"] == "Path is outside allowed workspace paths: /private/summary.md"
    assert await store.list_artifacts(run_id="run_1") == []


@pytest.mark.asyncio
async def test_sandbox_promote_file_fails_without_workspace_store() -> None:
    event_store = InMemoryAgentEventStore()
    tool = SandboxLocalTool(AgentEventWriter(event_store))
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.sandbox.execute", "agent.workspace.read", "agent.artifact.write"],
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_promote",
            tool_name="sandbox.promote_file",
            input={"path": "/reports/summary.md", "name": "Sandbox Summary"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "failed"
    assert result.error["message"] == "Sandbox file promotion requires a workspace store"


@pytest.mark.asyncio
async def test_sandbox_tool_delegates_execution_to_provider_and_emits_events() -> None:
    event_store = InMemoryAgentEventStore()
    provider = FakeSandboxProvider()
    tool = SandboxLocalTool(AgentEventWriter(event_store), provider=provider)
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.sandbox.execute"],
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="sandbox.run_python",
            input={"code": "result = 1", "timeout_ms": 250},
            requested_by="model",
        ),
        context,
    )
    events = await event_store.list_by_run("run_1")

    assert provider.requests == [SandboxExecutionRequest(code="result = 1", timeout_ms=250)]
    assert result.status == "completed"
    assert result.output["stdout"] == "fake stdout\n"
    assert result.output["result"] == {"ok": True}
    assert result.output["execution"] == {
        "language": "python",
        "timeout_ms": 250,
        "exit_code": None,
        "stdout_chars": len("fake stdout\n"),
        "stderr_chars": 0,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "result_type": "dict",
        "error_code": None,
        "timed_out": False,
    }
    assert result.output["diagnostics"] == {
        "sandbox_run_id": "sandbox_toolcall_1",
        "status": "completed",
        "language": "python",
        "execution": result.output["execution"],
        "workspace_effects": {
            "declared_count": 0,
            "persisted_count": 0,
            "promoted_count": 0,
            "paths": [],
            "persistence_error": None,
        },
        "error_code": None,
        "timed_out": False,
    }
    assert [event.type for event in events] == [
        "sandbox.started",
        "sandbox.stdout",
        "sandbox.completed",
    ]
    assert events[-1].payload["execution"] == result.output["execution"]
    assert events[-1].payload["diagnostics"] == result.output["diagnostics"]


@pytest.mark.asyncio
async def test_sandbox_tool_caps_timeout_with_run_policy() -> None:
    event_store = InMemoryAgentEventStore()
    provider = FakeSandboxProvider()
    tool = SandboxLocalTool(AgentEventWriter(event_store), provider=provider)
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.sandbox.execute"],
        sandbox_policy=AgentSandboxPolicy(enabled=True, timeout_ms=250),
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="sandbox.run_python",
            input={"code": "result = 1", "timeout_ms": 1000},
            requested_by="model",
        ),
        context,
    )
    events = await event_store.list_by_run("run_1")

    assert result.status == "completed"
    assert provider.requests == [SandboxExecutionRequest(code="result = 1", timeout_ms=250)]
    assert events[0].payload["timeout_ms"] == 250


@pytest.mark.asyncio
async def test_sandbox_tool_persists_declared_workspace_files_and_emits_events() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    tool = SandboxLocalTool(
        AgentEventWriter(event_store),
        store=store,
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="sandbox.run_python",
            input={
                "code": (
                    "workspace_files = ["
                    "{'path': '/reports/summary.md', 'content': '# Summary', 'media_type': 'text/markdown'}"
                    "]\n"
                    "result = 'created'"
                )
            },
            requested_by="model",
        ),
        context,
    )
    written = await store.read_workspace_file(workspace.id, "/reports/summary.md")
    events = await event_store.list_by_run("run_1")

    assert result.status == "completed"
    assert result.output["workspace_files"][0]["path"] == "/reports/summary.md"
    assert result.output["workspace_files"][0]["file"]["path"] == "/reports/summary.md"
    assert result.output["diagnostics"]["workspace_effects"] == {
        "declared_count": 1,
        "persisted_count": 1,
        "promoted_count": 0,
        "paths": ["/reports/summary.md"],
        "persistence_error": None,
    }
    assert written.content == "# Summary"
    assert written.media_type == "text/markdown"
    assert "workspace.file.created" in [event.type for event in events]
    workspace_event = next(event for event in events if event.type == "workspace.file.created")
    assert workspace_event.payload["source"] == "sandbox.run_python"
    assert workspace_event.payload["sandbox_run_id"] == "sandbox_toolcall_1"
    assert workspace_event.payload["path"] == "/reports/summary.md"


@pytest.mark.asyncio
async def test_sandbox_tool_promotes_declared_workspace_file_artifacts() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    tool = SandboxLocalTool(
        AgentEventWriter(event_store),
        store=store,
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write", "agent.artifact.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="sandbox.run_python",
            input={
                "code": (
                    "workspace_files = ["
                    "{"
                    "'path': '/reports/summary.md', "
                    "'content': '# Summary', "
                    "'media_type': 'text/markdown', "
                    "'artifact': {'name': 'Sandbox Summary', 'type': 'report'}"
                    "}"
                    "]\n"
                    "result = 'created'"
                )
            },
            requested_by="model",
        ),
        context,
    )
    artifacts = await store.list_artifacts(run_id="run_1")
    events = await event_store.list_by_run("run_1")

    assert result.status == "completed"
    promoted = result.output["workspace_files"][0]["artifact"]
    assert result.output["diagnostics"]["workspace_effects"] == {
        "declared_count": 1,
        "persisted_count": 1,
        "promoted_count": 1,
        "paths": ["/reports/summary.md"],
        "persistence_error": None,
    }
    assert promoted["artifact"]["name"] == "Sandbox Summary"
    assert promoted["artifact"]["type"] == "report"
    assert promoted["artifact"]["uri"] == "/reports/summary.md"
    assert promoted["artifact"]["metadata"]["source"] == "workspace_file"
    assert promoted["artifact"]["metadata"]["sandbox"]["sandbox_run_id"] == "sandbox_toolcall_1"
    assert [artifact.name for artifact in artifacts] == ["Sandbox Summary"]
    assert "artifact.created" in [event.type for event in events]
    artifact_event = next(event for event in events if event.type == "artifact.created")
    assert artifact_event.payload["artifact_id"] == promoted["artifact"]["id"]
    assert artifact_event.payload["source"] == "sandbox.run_python"


@pytest.mark.asyncio
async def test_sandbox_tool_rejects_artifact_promotion_without_artifact_scope() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    tool = SandboxLocalTool(
        AgentEventWriter(event_store),
        store=store,
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="sandbox.run_python",
            input={
                "code": (
                    "workspace_files = ["
                    "{"
                    "'path': '/reports/summary.md', "
                    "'content': '# Summary', "
                    "'artifact': {'name': 'Sandbox Summary', 'type': 'report'}"
                    "}"
                    "]"
                )
            },
            requested_by="model",
        ),
        context,
    )
    events = await event_store.list_by_run("run_1")

    assert result.status == "failed"
    assert "agent.artifact.write" in result.error["message"]
    assert (await store.list_workspace_files(workspace.id)) == []
    assert await store.list_artifacts(run_id="run_1") == []
    assert "workspace.file.created" not in [event.type for event in events]
    assert "artifact.created" not in [event.type for event in events]


@pytest.mark.asyncio
async def test_sandbox_tool_rejects_declared_workspace_files_outside_policy() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    event_store = InMemoryAgentEventStore()
    tool = SandboxLocalTool(
        AgentEventWriter(event_store),
        store=store,
    )
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["agent.sandbox.execute", "agent.workspace.write"],
        workspace_allowed_paths=["/reports"],
    )

    result = await tool.execute(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="sandbox.run_python",
            input={
                "code": (
                    "workspace_files = ["
                    "{'path': '/private/summary.md', 'content': '# Summary'}"
                    "]"
                )
            },
            requested_by="model",
        ),
        context,
    )
    events = await event_store.list_by_run("run_1")

    assert result.status == "failed"
    assert "outside allowed workspace paths" in result.error["message"]
    assert result.output["diagnostics"]["status"] == "failed"
    assert result.output["diagnostics"]["workspace_effects"] == {
        "declared_count": 1,
        "persisted_count": 0,
        "promoted_count": 0,
        "paths": [],
        "persistence_error": result.error,
    }
    assert "workspace.file.created" not in [event.type for event in events]
    assert (await store.list_workspace_files(workspace.id)) == []
    assert next(event for event in events if event.type == "sandbox.failed").payload["error"] == result.error
    assert (
        next(event for event in events if event.type == "sandbox.failed").payload["diagnostics"]
        == result.output["diagnostics"]
    )


@pytest.mark.asyncio
async def test_sandbox_run_python_emits_events_and_trace() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "sandbox.run_python",
                    {
                        "code": "print('rows', len(input_data['rows']))\nresult = sum(input_data['rows'])",
                        "input": {"rows": [1, 2, 3]},
                        "timeout_ms": 1000,
                    },
                ),
                Step.finish(),
            ]
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Process numbers",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]
    tool_completed = next(event for event in events if event.type == "tool.completed")
    spans = project_trace_spans(events)
    sandbox_span = next(span for span in spans if span.kind == "sandbox")

    assert run.status == AgentRunStatus.COMPLETED
    assert event_types.index("sandbox.started") < event_types.index("sandbox.stdout")
    assert event_types.index("sandbox.stdout") < event_types.index("sandbox.completed")
    assert event_types.index("sandbox.completed") < event_types.index("tool.completed")
    assert tool_completed.payload["output"]["result"] == 6
    assert tool_completed.payload["output"]["stdout"] == "rows 3\n"
    assert tool_completed.payload["output"]["execution"] == {
        "language": "python",
        "timeout_ms": 1000,
        "exit_code": 0,
        "stdout_chars": len("rows 3\n"),
        "stderr_chars": 0,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "result_type": "int",
        "error_code": None,
        "timed_out": False,
    }
    assert sandbox_span.status == "completed"
    assert sandbox_span.refs == {
        "language": "python",
        "timeout_ms": 1000,
        "exit_code": 0,
        "stdout_chars": len("rows 3\n"),
        "stderr_chars": 0,
        "timed_out": False,
    }


@pytest.mark.asyncio
async def test_sandbox_run_python_rejects_imports() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "sandbox.run_python",
                    {"code": "import os\nresult = os.listdir('/')"},
                ),
                Step.finish(),
            ]
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Try unsafe code",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    sandbox_failed = next(event for event in events if event.type == "sandbox.failed")
    spans = project_trace_spans(events)
    sandbox_span = next(span for span in spans if span.kind == "sandbox")

    assert run.status == AgentRunStatus.FAILED
    assert "import statements are not allowed" in sandbox_failed.payload["error"]["message"]
    assert sandbox_failed.payload["execution"]["error_code"] == "SandboxValidationError"
    assert sandbox_failed.payload["execution"]["timed_out"] is False
    assert sandbox_span.status == "failed"
