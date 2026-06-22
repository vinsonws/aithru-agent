import base64

import pytest

from aithru_agent.capabilities import (
    AgentRunContext,
    AithruCapabilityRouter,
    ToolPolicy,
)
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    InputLocalTool,
    MemoryLocalTool,
    ResearchLocalTool,
    TodoLocalTool,
    WorkbenchLocalTool,
    WorkspaceLocalTool,
)
from aithru_agent.domain import AgentToolCallRequest, MAX_WORKSPACE_IMAGE_BYTES
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
            "agent.research.write",
            "agent.input.write",
        ],
    )


def make_router(store: InMemoryAgentStore, policy: ToolPolicy | None = None) -> AithruCapabilityRouter:
    return AithruCapabilityRouter(
        adapters=[
            WorkspaceLocalTool(store),
            TodoLocalTool(store),
            ArtifactLocalTool(store),
            InputLocalTool(),
            MemoryLocalTool(store),
            ResearchLocalTool(store),
            WorkbenchLocalTool(store),
        ],
        policy=policy or ToolPolicy(require_approval_for_risk=[]),
    )


def test_local_tool_input_schemas_define_required_properties() -> None:
    store = InMemoryAgentStore()
    descriptors = [
        descriptor
        for adapter in [
            WorkspaceLocalTool(store),
            TodoLocalTool(store),
            ArtifactLocalTool(store),
            InputLocalTool(),
            MemoryLocalTool(store),
            ResearchLocalTool(store),
            WorkbenchLocalTool(store),
        ]
        for descriptor in adapter.list_tools()
    ]

    for descriptor in descriptors:
        required = set(descriptor.input_schema.get("required") or [])
        properties = set((descriptor.input_schema.get("properties") or {}).keys())
        assert required <= properties, descriptor.name


@pytest.mark.asyncio
async def test_router_lists_local_tools_with_risk_and_scopes() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)

    tools = await router.list_tools(context)
    by_name = {tool.name: tool for tool in tools}

    assert by_name["workspace.read_file"].risk_level == "read"
    assert by_name["workspace.view_image"].risk_level == "read"
    assert by_name["workspace.view_image"].required_scopes == ["agent.workspace.read"]
    assert by_name["workspace.view_image"].approval_policy == "never"
    assert "content_base64" in by_name["workspace.view_image"].output_schema["properties"]
    assert by_name["workspace.write_file"].risk_level == "write"
    assert by_name["workspace.patch_file"].risk_level == "write"
    assert by_name["workspace.patch_file"].required_scopes == ["agent.workspace.write"]
    assert "edits" in by_name["workspace.patch_file"].input_schema["properties"]
    assert by_name["todo.create"].required_scopes == ["agent.todo.write"]
    assert by_name["artifact.create"].required_scopes == ["agent.artifact.write"]
    assert by_name["input.request"].required_scopes == ["agent.input.write"]
    assert by_name["research.create_report"].required_scopes == [
        "agent.research.write",
        "agent.artifact.write",
    ]
    assert by_name["research.create_plan"].required_scopes == [
        "agent.research.write",
        "agent.todo.write",
    ]
    assert "workbench.workflow_draft.create" not in by_name
    assert "sections" in by_name["research.create_plan"].input_schema["properties"]


@pytest.mark.asyncio
async def test_router_lists_only_tools_allowed_by_run_scopes() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes = ["agent.workspace.read"]
    router = make_router(store)

    tool_names = [tool.name for tool in await router.list_tools(context)]

    assert "workspace.read_file" in tool_names
    assert "workspace.view_image" in tool_names
    assert "workspace.write_file" not in tool_names
    assert "memory.search" not in tool_names


@pytest.mark.asyncio
async def test_router_filters_workspace_view_image_by_allowed_tools() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes = ["agent.workspace.read"]
    router = make_router(store)

    context.allowed_tools = ["workspace.read_file"]
    read_only_names = [tool.name for tool in await router.list_tools(context)]
    context.allowed_tools = ["workspace.view_image"]
    image_only_names = [tool.name for tool in await router.list_tools(context)]

    assert "workspace.read_file" in read_only_names
    assert "workspace.view_image" not in read_only_names
    assert image_only_names == ["workspace.view_image"]


@pytest.mark.asyncio
async def test_router_denies_known_tool_with_missing_scope_authorization() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes = ["agent.workspace.read"]
    router = make_router(store)

    request = AgentToolCallRequest(
        id="toolcall_1",
        tool_name="workspace.write_file",
        input={"path": "/notes.md", "content": "# Notes"},
        requested_by="model",
    )

    prepared = await router.prepare_tool_call(request, context)
    result = await router.execute_tool_call(request, context)

    assert prepared.status == "denied"
    assert prepared.reason == "Missing required scope: agent.workspace.write"
    assert prepared.authorization.status == "denied"
    assert prepared.authorization.missing_scopes == ["agent.workspace.write"]
    assert result.status == "denied"
    assert result.authorization.status == "denied"
    assert result.audit.action == "tool.execute"
    assert result.audit.outcome == "denied"
    assert result.audit.authorization.missing_scopes == ["agent.workspace.write"]


@pytest.mark.asyncio
async def test_router_attaches_capability_audit_to_successful_tool_call() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="workspace.list_files",
            input={},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.authorization.status == "allowed"
    assert result.authorization.actor.user_id == "user_1"
    assert result.audit.action == "tool.execute"
    assert result.audit.outcome == "completed"
    assert result.audit.run_id == context.run_id
    assert result.audit.tool_name == "workspace.list_files"
    assert result.audit.authorization.required_scopes == ["agent.workspace.read"]


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
async def test_workspace_view_image_tool_returns_base64_for_allowed_workspace_image() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)
    image_bytes = b"\x89PNG\r\nimage"
    written = await store.write_workspace_file(
        workspace_id=context.workspace_id,
        path="/uploads/chart.png",
        content=image_bytes,
        media_type="image/png",
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_view_image",
            tool_name="workspace.view_image",
            input={"path": "/uploads/chart.png"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output == {
        "workspace_id": context.workspace_id,
        "path": "/uploads/chart.png",
        "media_type": "image/png",
        "size": len(image_bytes),
        "content_hash": written.content_hash,
        "content_encoding": "base64",
        "content_base64": base64.b64encode(image_bytes).decode("ascii"),
    }


@pytest.mark.asyncio
async def test_workspace_view_image_tool_denies_invalid_or_disallowed_files() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.workspace_allowed_paths = ["/uploads"]
    router = make_router(store)
    await store.write_workspace_file(
        workspace_id=context.workspace_id,
        path="/uploads/notes.txt",
        content="not an image",
        media_type="text/plain",
    )
    await store.write_workspace_file(
        workspace_id=context.workspace_id,
        path="/uploads/large.png",
        content=b"x" * (MAX_WORKSPACE_IMAGE_BYTES + 1),
        media_type="image/png",
    )
    await store.write_workspace_file(
        workspace_id=context.workspace_id,
        path="/uploads/blank.png",
        content=b"",
        media_type="image/png",
    )
    await store.write_workspace_file(
        workspace_id=context.workspace_id,
        path="/private/chart.png",
        content=b"image",
        media_type="image/png",
    )

    non_image = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_non_image",
            tool_name="workspace.view_image",
            input={"path": "/uploads/notes.txt"},
            requested_by="model",
        ),
        context,
    )
    oversized = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_oversized",
            tool_name="workspace.view_image",
            input={"path": "/uploads/large.png"},
            requested_by="model",
        ),
        context,
    )
    blank = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_blank",
            tool_name="workspace.view_image",
            input={"path": "/uploads/blank.png"},
            requested_by="model",
        ),
        context,
    )
    missing = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_missing",
            tool_name="workspace.view_image",
            input={"path": "/uploads/missing.png"},
            requested_by="model",
        ),
        context,
    )
    outside_policy = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_outside",
            tool_name="workspace.view_image",
            input={"path": "/private/chart.png"},
            requested_by="model",
        ),
        context,
    )

    assert non_image.status == "denied"
    assert "Unsupported image media type" in non_image.error["message"]
    assert oversized.status == "denied"
    assert "maximum image size" in oversized.error["message"]
    assert blank.status == "denied"
    assert "greater than 0" in blank.error["message"]
    assert missing.status == "denied"
    assert "Workspace file not found" in missing.error["message"]
    assert outside_policy.status == "denied"
    assert outside_policy.error["message"] == "Path is outside allowed workspace paths: /private/chart.png"


@pytest.mark.asyncio
async def test_workspace_patch_tool_applies_structured_text_edits() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)
    await store.write_workspace_file(
        workspace_id=context.workspace_id,
        path="/reports/report.md",
        content="# Draft\nOld title\nNeeds work.\nOld title\n",
        media_type="text/markdown",
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_patch",
            tool_name="workspace.patch_file",
            input={
                "path": "/reports/report.md",
                "edits": [
                    {
                        "old_text": "Old title",
                        "new_text": "Reviewed title",
                        "replace_all": True,
                        "expected_replacements": 2,
                    },
                    {
                        "old_text": "Needs work.",
                        "new_text": "Ready for review.",
                    },
                ],
            },
            requested_by="model",
        ),
        context,
    )
    patched = await store.read_workspace_file(context.workspace_id, "/reports/report.md")

    assert result.status == "completed"
    assert result.output["path"] == "/reports/report.md"
    assert result.output["replacement_count"] == 3
    assert result.output["version_before"] == 1
    assert result.output["version_after"] == 2
    assert result.output["file_version_before"] == 1
    assert result.output["file_version_after"] == 2
    assert result.output["size_before"] == len("# Draft\nOld title\nNeeds work.\nOld title\n".encode())
    assert result.output["size_after"] == len("# Draft\nReviewed title\nReady for review.\nReviewed title\n".encode())
    assert patched.content == "# Draft\nReviewed title\nReady for review.\nReviewed title\n"
    assert patched.media_type == "text/markdown"


@pytest.mark.asyncio
async def test_workspace_patch_tool_respects_workspace_path_policy() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.workspace_allowed_paths = ["/reports"]
    router = make_router(store)
    await store.write_workspace_file(
        workspace_id=context.workspace_id,
        path="/notes.md",
        content="draft",
        media_type="text/markdown",
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_patch_denied",
            tool_name="workspace.patch_file",
            input={
                "path": "/notes.md",
                "edits": [{"old_text": "draft", "new_text": "done"}],
            },
            requested_by="model",
        ),
        context,
    )
    unchanged = await store.read_workspace_file(context.workspace_id, "/notes.md")

    assert result.status == "denied"
    assert result.error["message"] == "Path is outside allowed workspace paths: /notes.md"
    assert unchanged.content == "draft"


@pytest.mark.asyncio
async def test_workbench_workflow_draft_tool_creates_structured_artifact() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)
    scoped_context = context.model_copy(
        update={"scopes": [*context.scopes, "agent.workbench.write"]}
    )

    assert "workbench.workflow_draft.create" not in [
        tool.name for tool in await router.list_tools(context)
    ]
    assert "workbench.workflow_draft.create" in [
        tool.name for tool in await router.list_tools(scoped_context)
    ]

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="workbench.workflow_draft.create",
            input={
                "title": "Review generated report",
                "summary": "Draft a future Workbench workflow for report review.",
                "suggested_steps": [
                    "Collect report artifact.",
                    "Ask a reviewer for approval.",
                    "Publish the approved report.",
                ],
                "required_inputs": ["Reviewer user id"],
                "risks": ["Needs human review before any Workbench workflow is created."],
                "open_questions": ["Who owns the final approval?"],
                "handoff_notes": "This is a non-executable draft for Workbench review.",
            },
            requested_by="model",
        ),
        scoped_context,
    )
    artifact = await store.get_artifact(result.output["id"])

    assert result.status == "completed"
    assert result.output["type"] == "workflow_draft"
    assert result.output["media_type"] == "application/vnd.aithru.workbench.workflow-draft+json"
    assert result.output["content"]["source_run_id"] == context.run_id
    assert result.output["content"]["source_workspace_id"] == context.workspace_id
    assert result.output["content"]["draft_kind"] == "workbench_workflow_draft"
    assert result.output["content"]["executable"] is False
    assert result.output["metadata"]["workbench"]["draft"] is True
    assert result.output["metadata"]["workbench"]["executable"] is False
    assert artifact is not None
    assert artifact.type == "workflow_draft"


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


@pytest.mark.asyncio
async def test_research_create_report_tool_creates_markdown_report_artifact() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="research.create_report",
            input={
                "title": "Aithru research",
                "query": "aithru deerflow parity",
                "sources": [
                    {
                        "title": "Aithru Agent",
                        "url": "https://example.com/aithru",
                        "snippet": "Harness backend.",
                        "section_id": "architecture",
                    }
                ],
            },
            requested_by="model",
        ),
        context,
    )

    artifacts = await store.list_artifacts(run_id=context.run_id)

    assert result.status == "completed"
    assert result.output["report"]["summary"] == "Collected 1 source for `aithru deerflow parity`."
    assert result.output["artifact"]["type"] == "report"
    assert result.output["artifact"]["media_type"] == "text/markdown"
    assert result.output["artifact"]["uri"] == "/reports/aithru-research.md"
    assert "# Aithru research" in result.output["artifact"]["content"]
    assert result.output["report"]["section_summary"] == [
        {"section_id": "architecture", "source_count": 1, "evidence_count": 1}
    ]
    assert result.output["artifact"]["metadata"]["section_count"] == 1
    assert result.output["artifact"]["metadata"]["section_summary"] == [
        {"section_id": "architecture", "source_count": 1, "evidence_count": 1}
    ]
    assert artifacts[0].id == result.output["artifact"]["id"]


@pytest.mark.asyncio
async def test_research_create_report_tool_auto_adds_limitations_from_blocked_todos() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)

    await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_plan",
            tool_name="research.create_plan",
            input={"query": "aithru deerflow parity"},
            requested_by="model",
        ),
        context,
    )
    search_todo = next(
        todo for todo in await store.list_todos(context.run_id) if todo.title == "Search sources"
    )
    await store.update_todo(search_todo.id, status="blocked")

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_report",
            tool_name="research.create_report",
            input={
                "title": "Blocked Aithru research",
                "query": "aithru deerflow parity",
            },
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output["report"]["status"] == "insufficient_evidence"
    assert result.output["report"]["limitations"] == [
        {
            "code": "research_search_blocked",
            "severity": "warning",
            "message": "Research source search was blocked before report creation.",
            "source_url": None,
        }
    ]
    assert result.output["artifact"]["metadata"]["limitation_count"] == 1
    assert "Research source search was blocked before report creation." in result.output[
        "artifact"
    ]["content"]


@pytest.mark.asyncio
async def test_research_create_report_tool_is_scope_controlled() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes = ["agent.artifact.write"]
    router = make_router(store)

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="research.create_report",
            input={
                "title": "Aithru research",
                "query": "aithru",
                "sources": [
                    {
                        "title": "Aithru Agent",
                        "url": "https://example.com/aithru",
                    }
                ],
            },
            requested_by="model",
        ),
        context,
    )

    assert result.status == "denied"
    assert result.error == {"message": "Missing required scope: agent.research.write"}
    assert result.authorization.missing_scopes == ["agent.research.write"]


@pytest.mark.asyncio
async def test_research_create_plan_tool_creates_runtime_todos() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="research.create_plan",
            input={
                "query": "aithru deerflow parity",
                "objective": "Compare backend completeness.",
                "sections": [
                    {
                        "section_id": "architecture",
                        "title": "Architecture",
                        "question": "How is the backend structured?",
                        "priority": "high",
                    }
                ],
            },
            requested_by="model",
        ),
        context,
    )
    todos = await store.list_todos(context.run_id)

    assert result.status == "completed"
    assert result.output["plan"]["query"] == "aithru deerflow parity"
    assert result.output["plan"]["sections"] == [
        {
            "section_id": "architecture",
            "title": "Architecture",
            "question": "How is the backend structured?",
            "priority": "high",
        }
    ]
    assert [todo["title"] for todo in result.output["todos"]] == [
        "Search sources",
        "Fetch and review sources",
        "Synthesize findings",
        "Create research report",
    ]
    assert [todo.title for todo in todos] == [
        "Search sources",
        "Fetch and review sources",
        "Synthesize findings",
        "Create research report",
    ]
    assert todos[0].description == "Find relevant sources for `aithru deerflow parity`."


@pytest.mark.asyncio
async def test_research_create_plan_tool_is_scope_controlled() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes = ["agent.research.write"]
    router = make_router(store)

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="research.create_plan",
            input={"query": "aithru"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "denied"
    assert result.error == {"message": "Missing required scope: agent.todo.write"}
    assert result.authorization.missing_scopes == ["agent.todo.write"]


@pytest.mark.asyncio
async def test_todo_update_cannot_modify_another_run_todo() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    other_workspace = await store.create_workspace(org_id=context.org_id)
    other_run = await store.create_run(
        org_id=context.org_id,
        actor_user_id=context.actor_user_id,
        source="api",
        goal="Other run",
        workspace_id=other_workspace.id,
    )
    other_todo = await store.create_todo(
        run_id=other_run.id,
        title="Other task",
        status="pending",
    )
    router = make_router(store)

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="todo.update",
            input={"todo_id": other_todo.id, "status": "done"},
            requested_by="model",
        ),
        context,
    )
    other_todos = await store.list_todos(other_run.id)

    assert result.status == "denied"
    assert result.error["message"] == f"Todo is outside current run: {other_todo.id}"
    assert other_todos[0].status == "pending"


@pytest.mark.asyncio
async def test_artifact_finalize_cannot_modify_another_run_artifact() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    other_workspace = await store.create_workspace(org_id=context.org_id)
    other_run = await store.create_run(
        org_id=context.org_id,
        actor_user_id=context.actor_user_id,
        source="api",
        goal="Other run",
        workspace_id=other_workspace.id,
    )
    other_artifact = await store.create_artifact(
        org_id=context.org_id,
        workspace_id=other_workspace.id,
        run_id=other_run.id,
        type="report",
        name="Other report",
    )
    router = make_router(store)

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="artifact.finalize",
            input={"artifact_id": other_artifact.id},
            requested_by="model",
        ),
        context,
    )
    persisted = await store.get_artifact(other_artifact.id)

    assert result.status == "denied"
    assert result.error["message"] == f"Artifact is outside current run: {other_artifact.id}"
    assert persisted.finalized_at is None


@pytest.mark.asyncio
async def test_memory_tools_remember_and_search_entries() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes.extend(["agent.memory.read", "agent.memory.write"])
    router = make_router(store)

    remember = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="memory.remember",
            input={"key": "project.style", "value": "Use concise Chinese summaries.", "scope": "user"},
            requested_by="model",
        ),
        context,
    )
    search = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_2",
            tool_name="memory.search",
            input={"query": "Chinese", "scope": "user"},
            requested_by="model",
        ),
        context,
    )

    assert remember.status == "completed"
    assert remember.output["key"] == "project.style"
    assert remember.output["scope_id"] == "user_1"
    assert search.status == "completed"
    assert [entry["key"] for entry in search.output["entries"]] == ["project.style"]


@pytest.mark.asyncio
async def test_memory_search_cannot_read_another_user_scope() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes.extend(["agent.memory.read"])
    router = make_router(store)
    await store.create_memory_entry(
        org_id=context.org_id,
        scope="user",
        scope_id="other_user",
        key="private.preference",
        value="Do not reveal.",
    )

    search = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="memory.search",
            input={"scope": "user", "scope_id": "other_user"},
            requested_by="model",
        ),
        context,
    )

    assert search.status == "denied"
    assert search.error["message"] == "Memory scope_id is outside the current run context: user"


@pytest.mark.asyncio
async def test_memory_search_without_scope_only_reads_current_context_scopes() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes.extend(["agent.memory.read"])
    router = make_router(store)
    await store.create_memory_entry(
        org_id=context.org_id,
        scope="user",
        scope_id=context.actor_user_id,
        key="current.preference",
        value="Visible current memory.",
    )
    await store.create_memory_entry(
        org_id=context.org_id,
        scope="user",
        scope_id="other_user",
        key="other.preference",
        value="Visible other memory.",
    )
    await store.create_memory_entry(
        org_id=context.org_id,
        scope="workspace",
        scope_id=context.workspace_id,
        key="workspace.note",
        value="Visible workspace memory.",
    )

    search = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="memory.search",
            input={"query": "Visible"},
            requested_by="model",
        ),
        context,
    )

    assert search.status == "completed"
    assert [entry["key"] for entry in search.output["entries"]] == [
        "current.preference",
        "workspace.note",
    ]


@pytest.mark.asyncio
async def test_memory_search_filters_private_memory_by_actor() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes.extend(["agent.memory.read"])
    router = make_router(store)
    await store.create_memory_entry(
        org_id=context.org_id,
        scope="workspace",
        scope_id=context.workspace_id,
        key="private.owned",
        value="Visible owned private memory.",
        owner=context.actor_user_id,
        visibility="private",
    )
    await store.create_memory_entry(
        org_id=context.org_id,
        scope="workspace",
        scope_id=context.workspace_id,
        key="private.other",
        value="Hidden other private memory.",
        owner="other_user",
        visibility="private",
    )
    await store.create_memory_entry(
        org_id=context.org_id,
        scope="workspace",
        scope_id=context.workspace_id,
        key="shared.workspace",
        value="Visible shared memory.",
        owner="other_user",
        visibility="shared",
    )

    search = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="memory.search",
            input={"scope": "workspace"},
            requested_by="model",
        ),
        context,
    )

    assert search.status == "completed"
    assert [entry["key"] for entry in search.output["entries"]] == [
        "private.owned",
        "shared.workspace",
    ]


@pytest.mark.asyncio
async def test_memory_remember_cannot_write_another_user_scope() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes.extend(["agent.memory.write"])
    router = make_router(store)

    remember = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="memory.remember",
            input={
                "scope": "user",
                "scope_id": "other_user",
                "key": "private.preference",
                "value": "Wrong user.",
            },
            requested_by="model",
        ),
        context,
    )
    entries = await store.list_memory_entries(org_id=context.org_id, scope="user")

    assert remember.status == "denied"
    assert remember.error["message"] == "Memory scope_id is outside the current run context: user"
    assert entries == []


@pytest.mark.asyncio
async def test_memory_tools_reject_unknown_scope() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    context.scopes.extend(["agent.memory.read", "agent.memory.write"])
    router = make_router(store)

    search = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="memory.search",
            input={"scope": "global"},
            requested_by="model",
        ),
        context,
    )
    remember = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_2",
            tool_name="memory.remember",
            input={"scope": "global", "key": "x", "value": "y"},
            requested_by="model",
        ),
        context,
    )

    assert search.status == "denied"
    assert search.error["message"] == "Unsupported memory scope: global"
    assert remember.status == "denied"
    assert remember.error["message"] == "Unsupported memory scope: global"
