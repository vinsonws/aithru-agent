import asyncio
from secrets import compare_digest
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from aithru_agent.application import AgentRuntime, create_agent_runtime
from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentArtifact,
    AgentMemoryEntry,
    AgentMessageRole,
    AgentRun,
    AgentRunHarnessOptions,
    AgentRunStatus,
    AgentThread,
    AgentWorkspace,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.harness import ContextBuilder
from aithru_agent.stream import format_sse_event
from aithru_agent.trace import project_trace_spans


class CreateThreadRequest(BaseModel):
    org_id: str = "org_1"
    owner_user_id: str = "user_1"
    title: str | None = None


class AppendMessageRequest(BaseModel):
    role: AgentMessageRole
    content: str = Field(min_length=1)


class CreateRunRequest(BaseModel):
    goal: str = Field(min_length=1)
    org_id: str = "org_1"
    actor_user_id: str = "user_1"
    scopes: list[str] | None = None
    harness_options: AgentRunHarnessOptions | None = None
    thread_id: str | None = None
    skill_id: str | None = None
    wait_for_completion: bool = False


class ResolveApprovalRequest(BaseModel):
    decision: AgentApprovalDecision
    approval_id: str | None = None
    comment: str | None = None


class AppendRunInputRequest(BaseModel):
    content: str = Field(min_length=1)


class WriteWorkspaceFileRequest(BaseModel):
    content: str
    media_type: str | None = None


class CreateMemoryEntryRequest(BaseModel):
    org_id: str = "org_1"
    scope: str
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    scope_id: str | None = None
    owner: str | None = None
    source: str | None = None
    confidence: float | None = None
    visibility: str | None = None
    retention: str | None = None


class CreateSubagentSpecRequest(BaseModel):
    org_id: str = "org_1"
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    allowed_tools: list[str] = Field(default_factory=list)


def create_app(runtime: AgentRuntime | None = None) -> FastAPI:
    rt = runtime or create_agent_runtime()
    app = FastAPI(title="Aithru Agent Backend")
    context_builder = ContextBuilder()

    @app.middleware("http")
    async def require_api_token(request: Request, call_next):
        token = rt.settings.api_token
        if token and request.url.path != "/api/agent/health":
            expected = f"Bearer {token}"
            actual = request.headers.get("authorization", "")
            if not compare_digest(actual, expected):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

    async def require_workspace_for_request(request: Request, workspace_id: str) -> AgentWorkspace:
        workspace = await rt.store.get_workspace(workspace_id)
        if not workspace or not await workspace_visible(request, workspace):
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    async def require_thread_for_request(request: Request, thread_id: str) -> AgentThread:
        thread = await rt.store.get_thread(thread_id)
        if not thread or not _thread_visible(request, thread):
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread

    async def require_run_for_request(request: Request, run_id: str) -> AgentRun:
        run = await rt.store.get_run(run_id)
        if not run or not _run_visible(request, run):
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    async def workspace_visible(request: Request, workspace: AgentWorkspace) -> bool:
        if not _org_visible(request, workspace.org_id):
            return False
        if workspace.run_id:
            run = await rt.store.get_run(workspace.run_id)
            return run is not None and _run_visible(request, run)
        if workspace.thread_id:
            thread = await rt.store.get_thread(workspace.thread_id)
            return thread is not None and _thread_visible(request, thread)
        return True

    async def approval_visible(request: Request, approval: AgentApproval) -> bool:
        run = await rt.store.get_run(approval.run_id)
        return run is not None and _run_visible(request, run)

    async def require_approval_for_request(request: Request, approval_id: str) -> AgentApproval:
        approval = await rt.store.get_approval(approval_id)
        if not approval or not await approval_visible(request, approval):
            raise HTTPException(status_code=404, detail="Approval not found")
        return approval

    async def artifact_visible(request: Request, artifact: AgentArtifact) -> bool:
        if not _org_visible(request, artifact.org_id):
            return False
        if artifact.run_id:
            run = await rt.store.get_run(artifact.run_id)
            return run is not None and _run_visible(request, run)
        workspace = await rt.store.get_workspace(artifact.workspace_id)
        return workspace is not None and await workspace_visible(request, workspace)

    async def require_artifact_for_request(request: Request, artifact_id: str) -> AgentArtifact:
        artifact = await rt.store.get_artifact(artifact_id)
        if not artifact or not await artifact_visible(request, artifact):
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact

    @app.get("/api/agent/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "service": "aithru-agent-backend"}

    @app.post("/api/agent/threads", status_code=201)
    async def create_thread(request: Request, body: CreateThreadRequest) -> dict[str, Any]:
        org_id = _identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
        owner_user_id = _identity_value(
            request,
            body,
            "owner_user_id",
            body.owner_user_id,
            "x-aithru-user-id",
        )
        thread = await rt.store.create_thread(
            org_id=org_id,
            owner_user_id=owner_user_id,
            title=body.title,
        )
        return thread.model_dump(mode="json")

    @app.get("/api/agent/threads")
    async def list_threads(request: Request) -> list[dict[str, Any]]:
        return [
            thread.model_dump(mode="json")
            for thread in await rt.store.list_threads()
            if _thread_visible(request, thread)
        ]

    @app.get("/api/agent/threads/{thread_id}")
    async def get_thread(request: Request, thread_id: str) -> dict[str, Any]:
        thread = await require_thread_for_request(request, thread_id)
        return thread.model_dump(mode="json")

    @app.post("/api/agent/threads/{thread_id}/messages", status_code=201)
    async def append_message(request: Request, thread_id: str, body: AppendMessageRequest) -> dict[str, Any]:
        await require_thread_for_request(request, thread_id)
        message = await rt.store.append_message(
            thread_id=thread_id,
            role=body.role,
            content=body.content,
        )
        return message.model_dump(mode="json")

    @app.get("/api/agent/threads/{thread_id}/messages")
    async def list_messages(request: Request, thread_id: str) -> list[dict[str, Any]]:
        await require_thread_for_request(request, thread_id)
        return [message.model_dump(mode="json") for message in await rt.store.list_messages(thread_id)]

    @app.post("/api/agent/runs", status_code=201)
    async def create_run(request: Request, body: CreateRunRequest) -> dict[str, Any]:
        scopes = body.scopes if body.scopes is not None else list(rt.settings.api_scopes)
        if rt.settings.api_token and not _scopes_allowed(scopes, rt.settings.api_scopes):
            raise HTTPException(status_code=403, detail="Requested scopes exceed API token scopes")
        org_id = _identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
        actor_user_id = _identity_value(
            request,
            body,
            "actor_user_id",
            body.actor_user_id,
            "x-aithru-user-id",
        )
        if body.thread_id:
            thread = await rt.store.get_thread(body.thread_id)
            if not thread:
                raise HTTPException(status_code=404, detail=f"Thread not found: {body.thread_id}")
            if not _thread_visible(request, thread):
                raise HTTPException(status_code=404, detail="Thread not found")
        run_kwargs = {
            "org_id": org_id,
            "actor_user_id": actor_user_id,
            "goal": body.goal,
            "scopes": scopes,
            "harness_options": body.harness_options,
            "thread_id": body.thread_id,
            "skill_id": body.skill_id,
        }
        try:
            if body.wait_for_completion:
                run = await rt.runner.start_run(**run_kwargs)
                latest = await rt.store.get_run(run.id)
                return (latest or run).model_dump(mode="json")
            run = await rt.worker.submit_run(**run_kwargs)
        except AgentError as err:
            status_code = 404 if err.code in {"NOT_FOUND", "SKILL_NOT_FOUND"} else 409
            raise HTTPException(status_code=status_code, detail=err.message) from err
        return run.model_dump(mode="json")

    @app.get("/api/agent/runs")
    async def list_runs(request: Request) -> list[dict[str, Any]]:
        return [
            run.model_dump(mode="json")
            for run in await rt.store.list_runs()
            if _run_visible(request, run)
        ]

    @app.get("/api/agent/runs/{run_id}")
    async def get_run(request: Request, run_id: str) -> dict[str, Any]:
        run = await require_run_for_request(request, run_id)
        return run.model_dump(mode="json")

    @app.get("/api/agent/runs/{run_id}/events")
    async def get_run_events(request: Request, run_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        await require_run_for_request(request, run_id)
        events = await rt.event_store.list_after_sequence(run_id, after_sequence)
        return [event.model_dump(mode="json") for event in events]

    @app.get("/api/agent/runs/{run_id}/trace")
    async def get_run_trace(request: Request, run_id: str) -> list[dict[str, Any]]:
        await require_run_for_request(request, run_id)
        events = await rt.event_store.list_by_run(run_id)
        return [span.model_dump(mode="json") for span in project_trace_spans(events)]

    @app.get("/api/agent/runs/{run_id}/snapshot")
    async def get_run_snapshot(request: Request, run_id: str) -> dict[str, Any]:
        run = await require_run_for_request(request, run_id)
        events = await rt.event_store.list_by_run(run_id)
        approvals = [
            approval
            for approval in await rt.store.list_approvals()
            if approval.run_id == run_id
        ]
        return {
            "run": run.model_dump(mode="json"),
            "events": [event.model_dump(mode="json") for event in events],
            "trace": [span.model_dump(mode="json") for span in project_trace_spans(events)],
            "todos": [
                todo.model_dump(mode="json")
                for todo in await rt.store.list_todos(run_id)
            ],
            "approvals": [approval.model_dump(mode="json") for approval in approvals],
            "workspace_files": [
                file.model_dump(mode="json")
                for file in await rt.store.list_workspace_files(run.workspace_id)
            ],
            "artifacts": [
                artifact.model_dump(mode="json")
                for artifact in await rt.store.list_artifacts(run_id=run_id)
            ],
            "subagents": [
                subagent_run.model_dump(mode="json")
                for subagent_run in await rt.store.list_subagent_runs(parent_run_id=run_id)
            ],
        }

    @app.get("/api/agent/runs/{run_id}/tools")
    async def get_run_tools(request: Request, run_id: str) -> list[dict[str, Any]]:
        run = await require_run_for_request(request, run_id)
        skill = rt.skill_resolver.resolve(run.skill_id) if run.skill_id else None
        context = context_builder.build(run, run.scopes, skill)
        tools = await rt.capability_router.list_tools(context)
        return [tool.model_dump(mode="json") for tool in tools]

    @app.get("/api/agent/runs/{run_id}/subagents")
    async def list_run_subagents(request: Request, run_id: str) -> list[dict[str, Any]]:
        await require_run_for_request(request, run_id)
        subagent_runs = await rt.store.list_subagent_runs(parent_run_id=run_id)
        return [subagent_run.model_dump(mode="json") for subagent_run in subagent_runs]

    @app.get("/api/agent/runs/{run_id}/stream")
    async def stream_run(
        request: Request,
        run_id: str,
        after_sequence: int = 0,
        follow: bool = False,
        poll_interval_seconds: float = 0.25,
        timeout_seconds: float = 30.0,
    ) -> Response:
        await require_run_for_request(request, run_id)
        if follow:
            return StreamingResponse(
                follow_run_events(
                    run_id,
                    after_sequence=after_sequence,
                    poll_interval_seconds=poll_interval_seconds,
                    timeout_seconds=timeout_seconds,
                ),
                media_type="text/event-stream",
            )
        events = await rt.event_store.list_after_sequence(run_id, after_sequence)
        return Response(
            "".join(format_sse_event(event) for event in events),
            media_type="text/event-stream",
        )

    @app.post("/api/agent/runs/{run_id}/input", status_code=201)
    async def append_run_input(request: Request, run_id: str, body: AppendRunInputRequest) -> dict[str, Any]:
        run = await require_run_for_request(request, run_id)
        if run.status in {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}:
            raise HTTPException(status_code=409, detail="Run is not accepting input")
        if not run.thread_id:
            raise HTTPException(status_code=409, detail="Run has no thread")
        message = await rt.store.append_message(
            thread_id=run.thread_id,
            role="user",
            content=body.content,
            run_id=run.id,
        )
        await rt.event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="message.created",
            source={"kind": "user", "id": run.actor_user_id},
            payload={"message_id": message.id, "role": "user"},
        )
        await rt.event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="message.completed",
            source={"kind": "user", "id": run.actor_user_id},
            payload={"message_id": message.id, "content": body.content},
        )
        return message.model_dump(mode="json")

    @app.post("/api/agent/runs/{run_id}/cancel")
    async def cancel_run(request: Request, run_id: str) -> dict[str, Any]:
        await require_run_for_request(request, run_id)
        try:
            run = await rt.runner.cancel_run(run_id)
        except AgentError as err:
            raise HTTPException(status_code=404, detail=err.message) from err
        return run.model_dump(mode="json")

    @app.post("/api/agent/runs/{run_id}/resume")
    async def resume_run(request: Request, run_id: str, body: ResolveApprovalRequest) -> dict[str, Any]:
        run = await require_run_for_request(request, run_id)
        approval_id = body.approval_id or run.current_approval_id
        if not approval_id:
            raise HTTPException(status_code=409, detail="Run is not waiting for approval")
        try:
            resumed = await rt.runner.resume_run(
                run_id,
                approval_id=approval_id,
                decision=body.decision,
                comment=body.comment,
            )
        except AgentError as err:
            raise HTTPException(status_code=409, detail=err.message) from err
        return resumed.model_dump(mode="json")

    @app.get("/api/agent/approvals")
    async def list_approvals(request: Request) -> list[dict[str, Any]]:
        approvals = []
        for approval in await rt.store.list_approvals():
            if await approval_visible(request, approval):
                approvals.append(approval.model_dump(mode="json"))
        return approvals

    @app.get("/api/agent/approvals/{approval_id}")
    async def get_approval(request: Request, approval_id: str) -> dict[str, Any]:
        approval = await require_approval_for_request(request, approval_id)
        return approval.model_dump(mode="json")

    @app.get("/api/agent/skills")
    async def list_skills() -> list[dict[str, Any]]:
        return [skill.model_dump(mode="json") for skill in rt.skill_resolver.list_skills()]

    @app.get("/api/agent/skills/{skill_id_or_key}")
    async def get_skill(skill_id_or_key: str) -> dict[str, Any]:
        skill = rt.skill_resolver.resolve(skill_id_or_key)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        return skill.model_dump(mode="json")

    @app.post("/api/agent/subagents", status_code=201)
    async def create_subagent_spec(request: Request, body: CreateSubagentSpecRequest) -> dict[str, Any]:
        org_id = _identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
        spec = await rt.store.create_subagent_spec(
            org_id=org_id,
            key=body.key,
            name=body.name,
            instructions=body.instructions,
            allowed_tools=body.allowed_tools,
        )
        return spec.model_dump(mode="json")

    @app.get("/api/agent/subagents")
    async def list_subagent_specs(request: Request, org_id: str | None = None) -> list[dict[str, Any]]:
        resolved_org_id = _identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
        specs = await rt.store.list_subagent_specs(resolved_org_id)
        return [spec.model_dump(mode="json") for spec in specs]

    @app.get("/api/agent/subagents/{key}")
    async def get_subagent_spec(request: Request, key: str, org_id: str | None = None) -> dict[str, Any]:
        resolved_org_id = _identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
        spec = await rt.store.get_subagent_spec(resolved_org_id, key)
        if not spec:
            raise HTTPException(status_code=404, detail="Subagent spec not found")
        return spec.model_dump(mode="json")

    @app.post("/api/agent/approvals/{approval_id}/resolve")
    async def resolve_approval(request: Request, approval_id: str, body: ResolveApprovalRequest) -> dict[str, Any]:
        approval = await require_approval_for_request(request, approval_id)
        try:
            await rt.runner.resume_run(
                approval.run_id,
                approval_id=approval_id,
                decision=body.decision,
                comment=body.comment,
            )
        except AgentError as err:
            raise HTTPException(status_code=409, detail=err.message) from err
        resolved = await rt.store.get_approval(approval_id)
        return resolved.model_dump(mode="json")

    @app.get("/api/agent/workspaces/{workspace_id}/files")
    async def list_workspace_files(request: Request, workspace_id: str) -> list[dict[str, Any]]:
        await require_workspace_for_request(request, workspace_id)
        return [
            file.model_dump(mode="json")
            for file in await rt.store.list_workspace_files(workspace_id)
        ]

    @app.get("/api/agent/workspaces/{workspace_id}/files/{path:path}")
    async def read_workspace_file(request: Request, workspace_id: str, path: str) -> dict[str, Any]:
        await require_workspace_for_request(request, workspace_id)
        try:
            content = await rt.store.read_workspace_file(workspace_id, path)
        except AgentError as err:
            raise HTTPException(status_code=404, detail=err.message) from err
        return {"path": "/" + path.lstrip("/"), **content.model_dump(mode="json")}

    @app.put("/api/agent/workspaces/{workspace_id}/files/{path:path}")
    async def write_workspace_file(
        request: Request,
        workspace_id: str,
        path: str,
        body: WriteWorkspaceFileRequest,
    ) -> dict[str, Any]:
        await require_workspace_for_request(request, workspace_id)
        file = await rt.store.write_workspace_file(
            workspace_id=workspace_id,
            path=path,
            content=body.content,
            media_type=body.media_type,
        )
        return file.model_dump(mode="json")

    @app.delete("/api/agent/workspaces/{workspace_id}/files/{path:path}")
    async def delete_workspace_file(request: Request, workspace_id: str, path: str) -> dict[str, str]:
        await require_workspace_for_request(request, workspace_id)
        try:
            return await rt.store.delete_workspace_file(workspace_id, path)
        except AgentError as err:
            raise HTTPException(status_code=404, detail=err.message) from err

    @app.get("/api/agent/artifacts")
    async def list_artifacts(request: Request, run_id: str | None = None) -> list[dict[str, Any]]:
        if run_id is not None:
            await require_run_for_request(request, run_id)
        artifacts = []
        for artifact in await rt.store.list_artifacts(run_id=run_id):
            if await artifact_visible(request, artifact):
                artifacts.append(artifact.model_dump(mode="json"))
        return artifacts

    @app.get("/api/agent/artifacts/{artifact_id}")
    async def get_artifact(request: Request, artifact_id: str) -> dict[str, Any]:
        artifact = await require_artifact_for_request(request, artifact_id)
        return artifact.model_dump(mode="json")

    @app.post("/api/agent/memory", status_code=201)
    async def create_memory_entry(request: Request, body: CreateMemoryEntryRequest) -> dict[str, Any]:
        org_id = _identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
        scope_id = _memory_scope_id_for_request(request, body.scope, body.scope_id)
        entry = await rt.store.create_memory_entry(
            org_id=org_id,
            scope=body.scope,
            scope_id=scope_id,
            key=body.key,
            value=body.value,
            owner=body.owner,
            source=body.source,
            confidence=body.confidence,
            visibility=body.visibility,
            retention=body.retention,
        )
        return entry.model_dump(mode="json")

    @app.get("/api/agent/memory")
    async def list_memory_entries(
        request: Request,
        org_id: str | None = None,
        scope: str | None = None,
        scope_id: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        resolved_org_id = _identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
        resolved_scope_id = _memory_scope_id_for_request(request, scope, scope_id)
        entries = await rt.store.list_memory_entries(
            org_id=resolved_org_id,
            scope=scope,
            scope_id=resolved_scope_id,
            query=query,
        )
        entries = _filter_memory_entries_for_request(request, entries)
        return [entry.model_dump(mode="json") for entry in entries]

    async def follow_run_events(
        run_id: str,
        *,
        after_sequence: int,
        poll_interval_seconds: float,
        timeout_seconds: float,
    ):
        cursor = after_sequence
        interval = max(0.01, poll_interval_seconds)
        deadline = asyncio.get_running_loop().time() + max(0.0, timeout_seconds)
        while True:
            events = await rt.event_store.list_after_sequence(run_id, cursor)
            if events:
                for event in events:
                    cursor = event.sequence
                    yield format_sse_event(event)
                continue

            run = await rt.store.get_run(run_id)
            if run is None or run.status in _TERMINAL_RUN_STATUSES:
                break
            if asyncio.get_running_loop().time() >= deadline:
                break
            await asyncio.sleep(interval)

    return app


app = create_app()


_TERMINAL_RUN_STATUSES = {
    AgentRunStatus.COMPLETED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
}


def _scopes_allowed(requested: list[str], allowed: list[str]) -> bool:
    if "*" in allowed:
        return True
    return all(scope in allowed for scope in requested)


def _identity_value(
    request: Request,
    body: BaseModel,
    field_name: str,
    body_value: str,
    header_name: str,
) -> str:
    header_value = request.headers.get(header_name)
    if header_value is None:
        return body_value
    if field_name in body.model_fields_set and body_value != header_value:
        raise HTTPException(status_code=403, detail="Request identity conflicts with authenticated context")
    return header_value


def _identity_query_value(
    request: Request,
    query_value: str | None,
    default_value: str,
    header_name: str,
) -> str:
    header_value = request.headers.get(header_name)
    if header_value is None:
        return query_value or default_value
    if query_value is not None and query_value != header_value:
        raise HTTPException(status_code=403, detail="Request identity conflicts with authenticated context")
    return header_value


def _memory_scope_id_for_request(request: Request, scope: str | None, scope_id: str | None) -> str | None:
    if scope != "user":
        return scope_id
    trusted_user_id = request.headers.get("x-aithru-user-id")
    if trusted_user_id is None:
        return scope_id
    if scope_id is not None and scope_id != trusted_user_id:
        raise HTTPException(status_code=403, detail="Request identity conflicts with authenticated context")
    return trusted_user_id


def _filter_memory_entries_for_request(
    request: Request,
    entries: list[AgentMemoryEntry],
) -> list[AgentMemoryEntry]:
    trusted_user_id = request.headers.get("x-aithru-user-id")
    if trusted_user_id is None:
        return entries
    return [
        entry
        for entry in entries
        if entry.scope != "user" or entry.scope_id == trusted_user_id
    ]


def _thread_visible(request: Request, thread: AgentThread) -> bool:
    user_id = request.headers.get("x-aithru-user-id")
    if not _org_visible(request, thread.org_id):
        return False
    if user_id is not None and thread.owner_user_id != user_id:
        return False
    return True


def _run_visible(request: Request, run: AgentRun) -> bool:
    user_id = request.headers.get("x-aithru-user-id")
    if not _org_visible(request, run.org_id):
        return False
    if user_id is not None and run.actor_user_id != user_id:
        return False
    return True


def _org_visible(request: Request, org_id: str) -> bool:
    trusted_org_id = request.headers.get("x-aithru-org-id")
    return trusted_org_id is None or org_id == trusted_org_id
