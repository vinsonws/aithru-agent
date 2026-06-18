"""Agent run event, trace, and snapshot routes."""

from typing import Any

from fastapi import APIRouter, Depends, Request

from aithru_agent.api.dependencies import ApiDependencies, api_deps, dump_model
from aithru_agent.trace import project_trace_spans

router = APIRouter()


@router.get("/api/agent/runs/{run_id}/events")
@router.get("/api/runs/{run_id}/events")
async def get_run_events(
    request: Request,
    run_id: str,
    after_sequence: int = 0,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    await deps.require_run(request, run_id)
    events = await deps.runtime.event_store.list_after_sequence(run_id, after_sequence)
    return [dump_model(event) for event in events]


@router.get("/api/threads/{thread_id}/runs/{run_id}/events")
async def get_thread_run_events(
    request: Request,
    thread_id: str,
    run_id: str,
    after_sequence: int = 0,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    await deps.require_thread_run(request, thread_id, run_id)
    events = await deps.runtime.event_store.list_after_sequence(run_id, after_sequence)
    return [dump_model(event) for event in events]


@router.get("/api/agent/runs/{run_id}/trace")
@router.get("/api/runs/{run_id}/trace")
async def get_run_trace(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    await deps.require_run(request, run_id)
    events = await deps.runtime.event_store.list_by_run(run_id)
    return [dump_model(span) for span in project_trace_spans(events)]


@router.get("/api/agent/runs/{run_id}/snapshot")
@router.get("/api/runs/{run_id}/snapshot")
async def get_run_snapshot(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    run = await deps.require_run(request, run_id)
    events = await deps.runtime.event_store.list_by_run(run_id)
    approvals = [
        approval
        for approval in await deps.runtime.store.list_approvals()
        if approval.run_id == run_id
    ]
    return {
        "run": dump_model(run),
        "events": [dump_model(event) for event in events],
        "trace": [dump_model(span) for span in project_trace_spans(events)],
        "todos": [
            dump_model(todo)
            for todo in await deps.runtime.store.list_todos(run_id)
        ],
        "approvals": [dump_model(approval) for approval in approvals],
        "workspace_files": [
            dump_model(file)
            for file in await deps.runtime.store.list_workspace_files(run.workspace_id)
        ],
        "artifacts": [
            dump_model(artifact)
            for artifact in await deps.runtime.store.list_artifacts(run_id=run_id)
        ],
        "subagents": [
            dump_model(subagent_run)
            for subagent_run in await deps.runtime.store.list_subagent_runs(parent_run_id=run_id)
        ],
    }

