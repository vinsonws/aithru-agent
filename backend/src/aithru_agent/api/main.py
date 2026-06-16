from typing import Any

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from aithru_agent.application import AgentRuntime, create_agent_runtime
from aithru_agent.domain import AgentApprovalDecision, AgentMessageRole
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
    scopes: list[str] = Field(default_factory=lambda: ["*"])
    thread_id: str | None = None
    skill_id: str | None = None
    wait_for_completion: bool = False


class ResolveApprovalRequest(BaseModel):
    decision: AgentApprovalDecision
    approval_id: str | None = None
    comment: str | None = None


class WriteWorkspaceFileRequest(BaseModel):
    content: Any
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

    @app.get("/api/agent/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "service": "aithru-agent-backend"}

    @app.post("/api/agent/threads", status_code=201)
    async def create_thread(body: CreateThreadRequest) -> dict[str, Any]:
        thread = await rt.store.create_thread(
            org_id=body.org_id,
            owner_user_id=body.owner_user_id,
            title=body.title,
        )
        return thread.model_dump(mode="json")

    @app.get("/api/agent/threads")
    async def list_threads() -> list[dict[str, Any]]:
        return [thread.model_dump(mode="json") for thread in await rt.store.list_threads()]

    @app.get("/api/agent/threads/{thread_id}")
    async def get_thread(thread_id: str) -> dict[str, Any]:
        thread = await rt.store.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread.model_dump(mode="json")

    @app.post("/api/agent/threads/{thread_id}/messages", status_code=201)
    async def append_message(thread_id: str, body: AppendMessageRequest) -> dict[str, Any]:
        message = await rt.store.append_message(
            thread_id=thread_id,
            role=body.role,
            content=body.content,
        )
        return message.model_dump(mode="json")

    @app.get("/api/agent/threads/{thread_id}/messages")
    async def list_messages(thread_id: str) -> list[dict[str, Any]]:
        return [message.model_dump(mode="json") for message in await rt.store.list_messages(thread_id)]

    @app.post("/api/agent/runs", status_code=201)
    async def create_run(body: CreateRunRequest) -> dict[str, Any]:
        run_kwargs = {
            "org_id": body.org_id,
            "actor_user_id": body.actor_user_id,
            "goal": body.goal,
            "scopes": body.scopes,
            "thread_id": body.thread_id,
            "skill_id": body.skill_id,
        }
        if body.wait_for_completion:
            run = await rt.runner.start_run(**run_kwargs)
            latest = await rt.store.get_run(run.id)
            return (latest or run).model_dump(mode="json")
        run = await rt.worker.submit_run(**run_kwargs)
        return run.model_dump(mode="json")

    @app.get("/api/agent/runs")
    async def list_runs() -> list[dict[str, Any]]:
        return [run.model_dump(mode="json") for run in await rt.store.list_runs()]

    @app.get("/api/agent/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        run = await rt.store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run.model_dump(mode="json")

    @app.get("/api/agent/runs/{run_id}/events")
    async def get_run_events(run_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        events = await rt.event_store.list_after_sequence(run_id, after_sequence)
        return [event.model_dump(mode="json") for event in events]

    @app.get("/api/agent/runs/{run_id}/trace")
    async def get_run_trace(run_id: str) -> list[dict[str, Any]]:
        run = await rt.store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        events = await rt.event_store.list_by_run(run_id)
        return [span.model_dump(mode="json") for span in project_trace_spans(events)]

    @app.get("/api/agent/runs/{run_id}/tools")
    async def get_run_tools(run_id: str) -> list[dict[str, Any]]:
        run = await rt.store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        skill = rt.skill_resolver.resolve(run.skill_id) if run.skill_id else None
        context = context_builder.build(run, run.scopes, skill)
        tools = await rt.capability_router.list_tools(context)
        return [tool.model_dump(mode="json") for tool in tools]

    @app.get("/api/agent/runs/{run_id}/subagents")
    async def list_run_subagents(run_id: str) -> list[dict[str, Any]]:
        run = await rt.store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        subagent_runs = await rt.store.list_subagent_runs(parent_run_id=run_id)
        return [subagent_run.model_dump(mode="json") for subagent_run in subagent_runs]

    @app.get("/api/agent/runs/{run_id}/stream")
    async def stream_run(run_id: str, after_sequence: int = 0) -> Response:
        events = await rt.event_store.list_after_sequence(run_id, after_sequence)
        return Response(
            "".join(format_sse_event(event) for event in events),
            media_type="text/event-stream",
        )

    @app.post("/api/agent/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict[str, Any]:
        try:
            run = await rt.runner.cancel_run(run_id)
        except AgentError as err:
            raise HTTPException(status_code=404, detail=err.message) from err
        return run.model_dump(mode="json")

    @app.post("/api/agent/runs/{run_id}/resume")
    async def resume_run(run_id: str, body: ResolveApprovalRequest) -> dict[str, Any]:
        run = await rt.store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
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
    async def list_approvals() -> list[dict[str, Any]]:
        return [approval.model_dump(mode="json") for approval in await rt.store.list_approvals()]

    @app.get("/api/agent/approvals/{approval_id}")
    async def get_approval(approval_id: str) -> dict[str, Any]:
        approval = await rt.store.get_approval(approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
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
    async def create_subagent_spec(body: CreateSubagentSpecRequest) -> dict[str, Any]:
        spec = await rt.store.create_subagent_spec(
            org_id=body.org_id,
            key=body.key,
            name=body.name,
            instructions=body.instructions,
            allowed_tools=body.allowed_tools,
        )
        return spec.model_dump(mode="json")

    @app.get("/api/agent/subagents")
    async def list_subagent_specs(org_id: str = "org_1") -> list[dict[str, Any]]:
        specs = await rt.store.list_subagent_specs(org_id)
        return [spec.model_dump(mode="json") for spec in specs]

    @app.get("/api/agent/subagents/{key}")
    async def get_subagent_spec(key: str, org_id: str = "org_1") -> dict[str, Any]:
        spec = await rt.store.get_subagent_spec(org_id, key)
        if not spec:
            raise HTTPException(status_code=404, detail="Subagent spec not found")
        return spec.model_dump(mode="json")

    @app.post("/api/agent/approvals/{approval_id}/resolve")
    async def resolve_approval(approval_id: str, body: ResolveApprovalRequest) -> dict[str, Any]:
        approval = await rt.store.get_approval(approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
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
    async def list_workspace_files(workspace_id: str) -> list[dict[str, Any]]:
        return [
            file.model_dump(mode="json")
            for file in await rt.store.list_workspace_files(workspace_id)
        ]

    @app.get("/api/agent/workspaces/{workspace_id}/files/{path:path}")
    async def read_workspace_file(workspace_id: str, path: str) -> dict[str, Any]:
        try:
            content = await rt.store.read_workspace_file(workspace_id, path)
        except AgentError as err:
            raise HTTPException(status_code=404, detail=err.message) from err
        return {"path": "/" + path.lstrip("/"), **content.model_dump(mode="json")}

    @app.put("/api/agent/workspaces/{workspace_id}/files/{path:path}")
    async def write_workspace_file(workspace_id: str, path: str, body: WriteWorkspaceFileRequest) -> dict[str, Any]:
        file = await rt.store.write_workspace_file(
            workspace_id=workspace_id,
            path=path,
            content=body.content,
            media_type=body.media_type,
        )
        return file.model_dump(mode="json")

    @app.delete("/api/agent/workspaces/{workspace_id}/files/{path:path}")
    async def delete_workspace_file(workspace_id: str, path: str) -> dict[str, str]:
        try:
            return await rt.store.delete_workspace_file(workspace_id, path)
        except AgentError as err:
            raise HTTPException(status_code=404, detail=err.message) from err

    @app.get("/api/agent/artifacts")
    async def list_artifacts(run_id: str | None = None) -> list[dict[str, Any]]:
        return [
            artifact.model_dump(mode="json")
            for artifact in await rt.store.list_artifacts(run_id=run_id)
        ]

    @app.get("/api/agent/artifacts/{artifact_id}")
    async def get_artifact(artifact_id: str) -> dict[str, Any]:
        artifact = await rt.store.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact.model_dump(mode="json")

    @app.post("/api/agent/memory", status_code=201)
    async def create_memory_entry(body: CreateMemoryEntryRequest) -> dict[str, Any]:
        entry = await rt.store.create_memory_entry(
            org_id=body.org_id,
            scope=body.scope,
            scope_id=body.scope_id,
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
        org_id: str = "org_1",
        scope: str | None = None,
        scope_id: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        entries = await rt.store.list_memory_entries(
            org_id=org_id,
            scope=scope,
            scope_id=scope_id,
            query=query,
        )
        return [entry.model_dump(mode="json") for entry in entries]

    return app


app = create_app()
