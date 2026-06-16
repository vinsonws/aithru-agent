from typing import Any

from fastapi import FastAPI, HTTPException, Response

from aithru_agent.application import AgentRuntime, create_agent_runtime
from aithru_agent.domain import AgentApprovalDecision
from aithru_agent.domain.errors import AgentError
from aithru_agent.stream import format_sse_event
from aithru_agent.trace import project_trace_spans


def create_app(runtime: AgentRuntime | None = None) -> FastAPI:
    rt = runtime or create_agent_runtime()
    app = FastAPI(title="Aithru Agent Backend")

    @app.get("/api/agent/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "service": "aithru-agent-backend"}

    @app.post("/api/agent/threads", status_code=201)
    async def create_thread(body: dict[str, Any]) -> dict[str, Any]:
        thread = await rt.store.create_thread(
            org_id=body.get("org_id", "org_1"),
            owner_user_id=body.get("owner_user_id", "user_1"),
            title=body.get("title"),
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
    async def append_message(thread_id: str, body: dict[str, Any]) -> dict[str, Any]:
        message = await rt.store.append_message(
            thread_id=thread_id,
            role=body["role"],
            content=body["content"],
        )
        return message.model_dump(mode="json")

    @app.get("/api/agent/threads/{thread_id}/messages")
    async def list_messages(thread_id: str) -> list[dict[str, Any]]:
        return [message.model_dump(mode="json") for message in await rt.store.list_messages(thread_id)]

    @app.post("/api/agent/runs", status_code=201)
    async def create_run(body: dict[str, Any]) -> dict[str, Any]:
        run = await rt.runner.start_run(
            org_id=body.get("org_id", "org_1"),
            actor_user_id=body.get("actor_user_id", "user_1"),
            goal=body["goal"],
            scopes=body.get("scopes", ["*"]),
            thread_id=body.get("thread_id"),
            skill_id=body.get("skill_id"),
        )
        latest = await rt.store.get_run(run.id)
        return (latest or run).model_dump(mode="json")

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

    @app.post("/api/agent/approvals/{approval_id}/resolve")
    async def resolve_approval(approval_id: str, body: dict[str, Any]) -> dict[str, Any]:
        approval = await rt.store.get_approval(approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        decision = AgentApprovalDecision(body["decision"])
        try:
            await rt.runner.resume_run(
                approval.run_id,
                approval_id=approval_id,
                decision=decision,
                comment=body.get("comment"),
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
    async def write_workspace_file(workspace_id: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        file = await rt.store.write_workspace_file(
            workspace_id=workspace_id,
            path=path,
            content=body["content"],
            media_type=body.get("media_type"),
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

    return app


app = create_app()
