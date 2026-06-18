"""Agent run routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from aithru_agent.api.dependencies import (
    ApiDependencies,
    AppendRunInputRequest,
    CreateRunRequest,
    api_deps,
    dump_model,
    identity_value,
    run_visible,
    scopes_allowed,
)
from aithru_agent.domain import AgentRun, AgentRunStatus
from aithru_agent.domain.errors import AgentError
from aithru_agent.stream import format_sse_event

router = APIRouter()


@router.post("/api/agent/runs", status_code=201)
async def create_run(
    request: Request,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    run = await _create_run(request, body, deps=deps)
    return dump_model(run)


@router.post("/api/threads/{thread_id}/runs", status_code=201)
async def create_thread_run(
    request: Request,
    thread_id: str,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    run = await _create_run(request, body, deps=deps, thread_id=thread_id)
    return dump_model(run)


@router.post("/api/runs/stream")
async def create_run_stream(
    request: Request,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> Response:
    run = await _create_run(request, body, deps=deps, force_wait=True)
    return await _run_events_response(run.id, deps)


@router.post("/api/threads/{thread_id}/runs/stream")
async def create_thread_run_stream(
    request: Request,
    thread_id: str,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> Response:
    run = await _create_run(request, body, deps=deps, thread_id=thread_id, force_wait=True)
    return await _run_events_response(run.id, deps)


@router.post("/api/runs/wait")
async def create_run_and_wait(
    request: Request,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    run = await _create_run(request, body, deps=deps, force_wait=True)
    return dump_model(run)


@router.get("/api/agent/runs")
@router.get("/api/runs")
async def list_runs(
    request: Request,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    return [
        dump_model(run)
        for run in await deps.runtime.store.list_runs()
        if run_visible(request, run)
    ]


@router.get("/api/threads/{thread_id}/runs")
async def list_thread_runs(
    request: Request,
    thread_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    await deps.require_thread(request, thread_id)
    return [
        dump_model(run)
        for run in await deps.runtime.store.list_runs()
        if run.thread_id == thread_id and run_visible(request, run)
    ]


@router.get("/api/agent/runs/{run_id}")
@router.get("/api/runs/{run_id}")
async def get_run(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    run = await deps.require_run(request, run_id)
    return dump_model(run)


@router.get("/api/threads/{thread_id}/runs/{run_id}")
async def get_thread_run(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return dump_model(run)


@router.get("/api/agent/runs/{run_id}/stream")
@router.get("/api/runs/{run_id}/stream")
async def stream_run(
    request: Request,
    run_id: str,
    after_sequence: int = 0,
    follow: bool = False,
    poll_interval_seconds: float = 0.25,
    timeout_seconds: float = 30.0,
    deps: ApiDependencies = Depends(api_deps),
) -> Response:
    await deps.require_run(request, run_id)
    return await _stream_existing_run(
        run_id,
        after_sequence=after_sequence,
        follow=follow,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
        deps=deps,
    )


@router.get("/api/threads/{thread_id}/runs/{run_id}/stream")
async def stream_thread_run(
    request: Request,
    thread_id: str,
    run_id: str,
    after_sequence: int = 0,
    follow: bool = False,
    poll_interval_seconds: float = 0.25,
    timeout_seconds: float = 30.0,
    deps: ApiDependencies = Depends(api_deps),
) -> Response:
    await deps.require_thread_run(request, thread_id, run_id)
    return await _stream_existing_run(
        run_id,
        after_sequence=after_sequence,
        follow=follow,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
        deps=deps,
    )


@router.get("/api/agent/runs/{run_id}/join")
@router.get("/api/runs/{run_id}/join")
async def join_run(
    request: Request,
    run_id: str,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.05,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    await deps.require_run(request, run_id)
    run = await deps.wait_for_run(
        run_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return dump_model(run)


@router.get("/api/threads/{thread_id}/runs/{run_id}/join")
async def join_thread_run(
    request: Request,
    thread_id: str,
    run_id: str,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.05,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    await deps.require_thread_run(request, thread_id, run_id)
    run = await deps.wait_for_run(
        run_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return dump_model(run)


@router.post("/api/agent/runs/{run_id}/cancel")
@router.post("/api/runs/{run_id}/cancel")
async def cancel_run(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    await deps.require_run(request, run_id)
    return await _cancel_run(run_id, deps)


@router.post("/api/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_thread_run(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    await deps.require_thread_run(request, thread_id, run_id)
    return await _cancel_run(run_id, deps)


@router.post("/api/agent/runs/{run_id}/input", status_code=201)
@router.post("/api/runs/{run_id}/input", status_code=201)
async def append_run_input(
    request: Request,
    run_id: str,
    body: AppendRunInputRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    run = await deps.require_run(request, run_id)
    if run.status in {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Run is not accepting input")
    if not run.thread_id:
        raise HTTPException(status_code=409, detail="Run has no thread")
    message = await deps.runtime.store.append_message(
        thread_id=run.thread_id,
        role="user",
        content=body.content,
        run_id=run.id,
    )
    await deps.runtime.event_writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="message.created",
        source={"kind": "user", "id": run.actor_user_id},
        payload={"message_id": message.id, "role": "user"},
    )
    await deps.runtime.event_writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="message.completed",
        source={"kind": "user", "id": run.actor_user_id},
        payload={"message_id": message.id, "content": body.content},
    )
    return dump_model(message)


@router.get("/api/agent/runs/{run_id}/tools")
@router.get("/api/runs/{run_id}/tools")
async def get_run_tools(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    run = await deps.require_run(request, run_id)
    skill = deps.resolve_run_skill(run)
    context = deps.context_builder.build(run, run.scopes, skill)
    tools = await deps.runtime.capability_router.list_tools(context)
    return [dump_model(tool) for tool in tools]


@router.get("/api/agent/runs/{run_id}/subagents")
@router.get("/api/runs/{run_id}/subagents")
async def list_run_subagents(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    await deps.require_run(request, run_id)
    subagent_runs = await deps.runtime.store.list_subagent_runs(parent_run_id=run_id)
    return [dump_model(subagent_run) for subagent_run in subagent_runs]


async def _create_run(
    request: Request,
    body: CreateRunRequest,
    *,
    deps: ApiDependencies,
    thread_id: str | None = None,
    force_wait: bool = False,
) -> AgentRun:
    scopes = body.scopes if body.scopes is not None else list(deps.runtime.settings.api_scopes)
    if deps.runtime.settings.api_token and not scopes_allowed(scopes, deps.runtime.settings.api_scopes):
        raise HTTPException(status_code=403, detail="Requested scopes exceed API token scopes")

    org_id = identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
    actor_user_id = identity_value(
        request,
        body,
        "actor_user_id",
        body.actor_user_id,
        "x-aithru-user-id",
    )
    resolved_thread_id = thread_id or body.thread_id
    if thread_id and body.thread_id and body.thread_id != thread_id:
        raise HTTPException(status_code=409, detail="Body thread_id does not match route thread_id")
    if resolved_thread_id:
        thread = await deps.runtime.store.get_thread(resolved_thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread not found: {resolved_thread_id}")
        if not await _thread_access_allowed(request, thread_id=resolved_thread_id, deps=deps):
            raise HTTPException(status_code=404, detail="Thread not found")

    run_kwargs = {
        "org_id": org_id,
        "actor_user_id": actor_user_id,
        "goal": body.goal,
        "scopes": scopes,
        "harness_options": body.harness_options,
        "thread_id": resolved_thread_id,
        "skill_id": body.skill_id,
    }
    try:
        if force_wait or body.wait_for_completion:
            run = await deps.runtime.runner.start_run(**run_kwargs)
            return await deps.runtime.store.get_run(run.id) or run
        return await deps.runtime.worker.submit_run(**run_kwargs)
    except AgentError as err:
        status_code = 404 if err.code in {"NOT_FOUND", "SKILL_NOT_FOUND"} else 409
        raise HTTPException(status_code=status_code, detail=err.message) from err


async def _thread_access_allowed(request: Request, *, thread_id: str, deps: ApiDependencies) -> bool:
    try:
        await deps.require_thread(request, thread_id)
    except HTTPException:
        return False
    return True


async def _stream_existing_run(
    run_id: str,
    *,
    after_sequence: int,
    follow: bool,
    poll_interval_seconds: float,
    timeout_seconds: float,
    deps: ApiDependencies,
) -> Response:
    if follow:
        return StreamingResponse(
            deps.follow_run_events(
                run_id,
                after_sequence=after_sequence,
                poll_interval_seconds=poll_interval_seconds,
                timeout_seconds=timeout_seconds,
            ),
            media_type="text/event-stream",
        )
    events = await deps.runtime.event_store.list_after_sequence(run_id, after_sequence)
    return Response(
        "".join(format_sse_event(event) for event in events),
        media_type="text/event-stream",
    )


async def _run_events_response(run_id: str, deps: ApiDependencies) -> Response:
    events = await deps.runtime.event_store.list_by_run(run_id)
    return Response(
        "".join(format_sse_event(event) for event in events),
        media_type="text/event-stream",
    )


async def _cancel_run(run_id: str, deps: ApiDependencies) -> dict[str, Any]:
    try:
        run = await deps.runtime.runner.cancel_run(run_id)
    except AgentError as err:
        status_code = 404 if err.code == "NOT_FOUND" else 409
        raise HTTPException(status_code=status_code, detail=err.message) from err
    return dump_model(run)

