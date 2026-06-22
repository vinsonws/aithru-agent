"""Agent run routes."""

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

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
from aithru_agent.api.snapshots import (
    ResearchContinuationAction,
    ResearchContinuationSnapshot,
    RunInspectionHealth,
    RunInspectionSummary,
    RunSandboxDiagnostic,
    RunSandboxOperatorAction,
    RunSandboxOperatorActionKind,
    build_research_continuation_snapshot,
    build_run_inspection_summary,
)
from aithru_agent.domain import (
    AgentMemoryRecall,
    AgentMessage,
    AgentRun,
    AgentRunHarnessOptions,
    AgentRunOperatorFollowUpOptions,
    AgentRunResearchContinuationOptions,
    AgentRunStatus,
    AgentSubagentRun,
    AgentToolDescriptor,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.harness import ContextPacketBuilder
from aithru_agent.stream import format_sse_event
from aithru_agent.trace import project_trace_spans

router = APIRouter()


RunListOrderBy = Literal[
    "started_at",
    "completed_at",
    "status",
    "health",
    "sandbox_operator_action_count",
]
RunListOrderDirection = Literal["asc", "desc"]


class RunListQuery(BaseModel):
    status: AgentRunStatus | None = None
    skill_id: str | None = None
    health: RunInspectionHealth | None = None
    needs_attention: bool | None = None
    external_run_stale: bool | None = None
    sandbox_failed: bool | None = None
    sandbox_side_effects: bool | None = None
    needs_operator_action: bool | None = None
    sandbox_operator_action_kind: RunSandboxOperatorActionKind | None = None
    operator_follow_up: bool | None = None
    operator_follow_up_source_run_id: str | None = None
    operator_follow_up_action_kind: RunSandboxOperatorActionKind | None = None
    include_meta: bool = False
    order_by: RunListOrderBy | None = None
    order_direction: RunListOrderDirection = "asc"
    limit: int | None = Field(default=None, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("skill_id", "operator_follow_up_source_run_id")
    @classmethod
    def _optional_string_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class RunListItem(AgentRun):
    summary: RunInspectionSummary


class RunListPage(BaseModel):
    items: list[RunListItem]
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int | None = None
    offset: int = Field(ge=0)
    order_by: RunListOrderBy | None = None
    order_direction: RunListOrderDirection
    sandbox_operator_action_counts: dict[RunSandboxOperatorActionKind, int] = Field(
        default_factory=dict
    )
    operator_follow_up_action_counts: dict[RunSandboxOperatorActionKind, int] = Field(
        default_factory=dict
    )
    operator_follow_up_source_run_counts: dict[str, int] = Field(default_factory=dict)


RunListResponse = list[RunListItem] | RunListPage


class RunDetailResponse(AgentRun):
    summary: RunInspectionSummary


class ResearchContinuationRunResult(BaseModel):
    source_run_id: str = Field(min_length=1)
    continuation_status: str = Field(min_length=1)
    target_section_ids: list[str] = Field(default_factory=list)
    selected_actions: list[ResearchContinuationAction] = Field(default_factory=list)
    created_run: AgentRun


class OperatorFollowUpRunResult(BaseModel):
    source_run_id: str = Field(min_length=1)
    operator_follow_up: AgentRunOperatorFollowUpOptions
    selected_actions: list[RunSandboxOperatorAction] = Field(default_factory=list)
    created_run: AgentRun


class CreateResearchContinuationRunRequest(BaseModel):
    action_ids: list[str] | None = None
    goal: str | None = Field(default=None, min_length=1)
    instructions: str | None = Field(default=None, min_length=1)
    scopes: list[str] | None = None

    @model_validator(mode="after")
    def _action_ids_must_not_be_empty(self) -> "CreateResearchContinuationRunRequest":
        if self.action_ids is not None and not self.action_ids:
            raise ValueError("action_ids must not be empty")
        return self


class CreateOperatorActionFollowUpRunRequest(BaseModel):
    action_kind: RunSandboxOperatorActionKind
    goal: str | None = Field(default=None, min_length=1)
    instructions: str | None = Field(default=None, min_length=1)
    scopes: list[str] | None = None


@router.post("/api/runs", status_code=201, response_model=AgentRun)
async def create_run(
    request: Request,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRun:
    return await _create_run(request, body, deps=deps)


@router.post(
    "/api/threads/{thread_id}/runs",
    status_code=201,
    response_model=AgentRun,
)
async def create_thread_run(
    request: Request,
    thread_id: str,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRun:
    return await _create_run(request, body, deps=deps, thread_id=thread_id)


@router.post("/api/runs/stream")
async def create_run_stream(
    request: Request,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> Response:
    run = await _create_run(request, body, deps=deps)
    return _run_live_stream_response(run.id, deps)


@router.post("/api/threads/{thread_id}/runs/stream")
async def create_thread_run_stream(
    request: Request,
    thread_id: str,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> Response:
    run = await _create_run(request, body, deps=deps, thread_id=thread_id)
    return _run_live_stream_response(run.id, deps)


@router.post("/api/runs/wait", response_model=AgentRun)
async def create_run_and_wait(
    request: Request,
    body: CreateRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRun:
    return await _create_run(request, body, deps=deps, force_wait=True)


@router.get("/api/runs", response_model=RunListResponse)
async def list_runs(
    request: Request,
    query: RunListQuery = Depends(),
    deps: ApiDependencies = Depends(api_deps),
) -> RunListResponse:
    runs = [
        run
        for run in await deps.runtime.store.list_runs()
        if run_visible(request, run) and _run_matches_list_query(run, query)
    ]
    return _dump_run_list_response(await _build_run_list_page(runs, query, deps), query)


@router.get("/api/threads/{thread_id}/runs", response_model=RunListResponse)
async def list_thread_runs(
    request: Request,
    thread_id: str,
    query: RunListQuery = Depends(),
    deps: ApiDependencies = Depends(api_deps),
) -> RunListResponse:
    await deps.require_thread(request, thread_id)
    runs = [
        run
        for run in await deps.runtime.store.list_runs()
        if run.thread_id == thread_id and run_visible(request, run) and _run_matches_list_query(run, query)
    ]
    return _dump_run_list_response(await _build_run_list_page(runs, query, deps), query)


@router.get("/api/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> RunDetailResponse:
    run = await deps.require_run(request, run_id)
    return await _run_detail_response(run, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}",
    response_model=RunDetailResponse,
)
async def get_thread_run(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> RunDetailResponse:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _run_detail_response(run, deps)


@router.get("/api/runs/{run_id}/summary", response_model=RunInspectionSummary)
async def get_run_summary(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> RunInspectionSummary:
    run = await deps.require_run(request, run_id)
    return await _build_run_inspection_summary_for_run(run, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/summary",
    response_model=RunInspectionSummary,
)
async def get_thread_run_summary(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> RunInspectionSummary:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _build_run_inspection_summary_for_run(run, deps)


@router.get("/api/runs/{run_id}/memory-recall", response_model=AgentMemoryRecall)
async def get_run_memory_recall(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMemoryRecall:
    run = await deps.require_run(request, run_id)
    return await ContextPacketBuilder().build_memory_recall(run, deps.runtime.store)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/memory-recall",
    response_model=AgentMemoryRecall,
)
async def get_thread_run_memory_recall(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMemoryRecall:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await ContextPacketBuilder().build_memory_recall(run, deps.runtime.store)


@router.post(
    "/api/runs/{run_id}/research/continue",
    status_code=201,
    response_model=ResearchContinuationRunResult,
)
async def create_research_continuation_run(
    request: Request,
    run_id: str,
    body: CreateResearchContinuationRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchContinuationRunResult:
    run = await deps.require_run(request, run_id)
    return await _create_research_continuation_run(run, body, deps)


@router.post(
    "/api/threads/{thread_id}/runs/{run_id}/research/continue",
    status_code=201,
    response_model=ResearchContinuationRunResult,
)
async def create_thread_research_continuation_run(
    request: Request,
    thread_id: str,
    run_id: str,
    body: CreateResearchContinuationRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchContinuationRunResult:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _create_research_continuation_run(run, body, deps)


@router.post(
    "/api/runs/{run_id}/operator-actions/follow-up",
    status_code=201,
    response_model=OperatorFollowUpRunResult,
)
async def create_operator_action_follow_up_run(
    request: Request,
    run_id: str,
    body: CreateOperatorActionFollowUpRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> OperatorFollowUpRunResult:
    run = await deps.require_run(request, run_id)
    return await _create_operator_action_follow_up_run(run, body, deps)


@router.post(
    "/api/threads/{thread_id}/runs/{run_id}/operator-actions/follow-up",
    status_code=201,
    response_model=OperatorFollowUpRunResult,
)
async def create_thread_operator_action_follow_up_run(
    request: Request,
    thread_id: str,
    run_id: str,
    body: CreateOperatorActionFollowUpRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> OperatorFollowUpRunResult:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _create_operator_action_follow_up_run(run, body, deps)


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


@router.get("/api/runs/{run_id}/join", response_model=AgentRun)
async def join_run(
    request: Request,
    run_id: str,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.05,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRun:
    await deps.require_run(request, run_id)
    run = await deps.wait_for_run(
        run_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return run


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/join",
    response_model=AgentRun,
)
async def join_thread_run(
    request: Request,
    thread_id: str,
    run_id: str,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.05,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRun:
    await deps.require_thread_run(request, thread_id, run_id)
    run = await deps.wait_for_run(
        run_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return run


@router.post("/api/runs/{run_id}/cancel", response_model=AgentRun)
async def cancel_run(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRun:
    await deps.require_run(request, run_id)
    return await _cancel_run(run_id, deps)


@router.post(
    "/api/threads/{thread_id}/runs/{run_id}/cancel",
    response_model=AgentRun,
)
async def cancel_thread_run(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRun:
    await deps.require_thread_run(request, thread_id, run_id)
    return await _cancel_run(run_id, deps)


@router.post("/api/runs/{run_id}/input", status_code=201, response_model=AgentMessage)
async def append_run_input(
    request: Request,
    run_id: str,
    body: AppendRunInputRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMessage:
    run = await deps.require_run(request, run_id)
    return await _append_run_input(run=run, body=body, deps=deps)


@router.post(
    "/api/threads/{thread_id}/runs/{run_id}/input",
    status_code=201,
    response_model=AgentMessage,
)
async def append_thread_run_input(
    request: Request,
    thread_id: str,
    run_id: str,
    body: AppendRunInputRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMessage:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _append_run_input(run=run, body=body, deps=deps)


async def _append_run_input(
    *,
    run: AgentRun,
    body: AppendRunInputRequest,
    deps: ApiDependencies,
) -> AgentMessage:
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
    if run.status == AgentRunStatus.WAITING_INPUT:
        await deps.runtime.event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="input.received",
            source={"kind": "user", "id": run.actor_user_id},
            payload={"message_id": message.id, "content": body.content},
        )
        try:
            await deps.runtime.worker.resume_waiting_input(run.id)
        except AgentError as err:
            raise HTTPException(status_code=409, detail=err.message) from err
    return message


@router.get("/api/runs/{run_id}/tools", response_model=list[AgentToolDescriptor])
async def get_run_tools(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentToolDescriptor]:
    run = await deps.require_run(request, run_id)
    skill = deps.resolve_run_skill(run)
    context = deps.context_builder.build(run, run.scopes, skill)
    return await deps.runtime.capability_router.list_tools(context)


@router.get("/api/runs/{run_id}/subagents", response_model=list[AgentSubagentRun])
async def list_run_subagents(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentSubagentRun]:
    await deps.require_run(request, run_id)
    return await deps.runtime.store.list_subagent_runs(parent_run_id=run_id)


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
        "retry_policy": body.retry_policy,
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


async def _create_research_continuation_run(
    source_run: AgentRun,
    body: CreateResearchContinuationRunRequest,
    deps: ApiDependencies,
) -> ResearchContinuationRunResult:
    scopes = body.scopes if body.scopes is not None else list(source_run.scopes)
    if deps.runtime.settings.api_token and not scopes_allowed(scopes, deps.runtime.settings.api_scopes):
        raise HTTPException(status_code=403, detail="Requested scopes exceed API token scopes")

    events = await deps.runtime.event_store.list_by_run(source_run.id)
    trace = project_trace_spans(events)
    todos = await deps.runtime.store.list_todos(source_run.id)
    artifacts = await deps.runtime.store.list_artifacts(run_id=source_run.id)
    continuation = build_research_continuation_snapshot(
        run=source_run,
        events=events,
        todos=todos,
        artifacts=artifacts,
        trace=trace,
    )
    if not continuation.actions:
        raise HTTPException(status_code=409, detail="Run has no research continuation actions")
    selected_actions = _selected_research_continuation_actions(
        continuation=continuation,
        action_ids=body.action_ids,
    )
    action_ids = [action.action_id for action in selected_actions]
    target_section_ids = _selected_research_continuation_target_section_ids(selected_actions)
    harness_options = _continuation_harness_options(
        source_run=source_run,
        continuation=continuation,
        selected_actions=selected_actions,
        action_ids=action_ids,
        target_section_ids=target_section_ids,
        extra_instructions=body.instructions,
    )
    created_run = await deps.runtime.store.create_run(
        org_id=source_run.org_id,
        actor_user_id=source_run.actor_user_id,
        source="api",
        goal=body.goal or _continuation_goal(source_run, continuation),
        workspace_id=source_run.workspace_id,
        scopes=scopes,
        harness_options=harness_options,
        retry_policy=source_run.retry_policy,
        thread_id=source_run.thread_id,
        skill_id=source_run.skill_id,
    )
    continuation_payload = {
        "source_run_id": source_run.id,
        "child_run_id": created_run.id,
        "action_ids": action_ids,
        "target_section_ids": target_section_ids,
        "continuation_status": continuation.status,
        "query": continuation.query,
    }
    await deps.runtime.event_writer.write(
        run_id=created_run.id,
        thread_id=created_run.thread_id,
        type="run.created",
        source={"kind": "harness"},
        payload={
            "status": "queued",
            "workspace_id": created_run.workspace_id,
            "continuation": continuation_payload,
        },
    )
    await deps.runtime.event_writer.write(
        run_id=source_run.id,
        thread_id=source_run.thread_id,
        type="research.continuation.created",
        source={"kind": "harness"},
        payload=continuation_payload,
    )
    deps.runtime.worker.queue.enqueue(created_run.id)
    return ResearchContinuationRunResult(
        source_run_id=source_run.id,
        continuation_status=continuation.status,
        target_section_ids=target_section_ids,
        selected_actions=selected_actions,
        created_run=created_run,
    )


async def _create_operator_action_follow_up_run(
    source_run: AgentRun,
    body: CreateOperatorActionFollowUpRunRequest,
    deps: ApiDependencies,
) -> OperatorFollowUpRunResult:
    scopes = body.scopes if body.scopes is not None else list(source_run.scopes)
    if deps.runtime.settings.api_token and not scopes_allowed(scopes, deps.runtime.settings.api_scopes):
        raise HTTPException(status_code=403, detail="Requested scopes exceed API token scopes")

    summary = await _build_run_inspection_summary_for_run(source_run, deps)
    if not summary.sandbox_operator_actions:
        raise HTTPException(status_code=409, detail="Run has no operator actions")
    selected = _selected_sandbox_operator_actions(summary, body.action_kind)
    follow_up = _operator_follow_up_options(source_run=source_run, selected=selected)
    harness_options = _operator_follow_up_harness_options(
        source_run=source_run,
        follow_up=follow_up,
        selected=selected,
        extra_instructions=body.instructions,
    )
    created_run = await deps.runtime.store.create_run(
        org_id=source_run.org_id,
        actor_user_id=source_run.actor_user_id,
        source="api",
        goal=body.goal or _operator_follow_up_goal(source_run, follow_up),
        workspace_id=source_run.workspace_id,
        scopes=scopes,
        harness_options=harness_options,
        retry_policy=source_run.retry_policy,
        thread_id=source_run.thread_id,
        skill_id=source_run.skill_id,
    )
    follow_up_payload = {
        "source_run_id": source_run.id,
        "child_run_id": created_run.id,
        "operator_follow_up": dump_model(follow_up),
    }
    await deps.runtime.event_writer.write(
        run_id=created_run.id,
        thread_id=created_run.thread_id,
        type="run.created",
        source={"kind": "harness"},
        payload={
            "status": "queued",
            "workspace_id": created_run.workspace_id,
            "operator_follow_up": dump_model(follow_up),
        },
    )
    await deps.runtime.event_writer.write(
        run_id=source_run.id,
        thread_id=source_run.thread_id,
        type="operator_action.follow_up.created",
        source={"kind": "harness"},
        payload=follow_up_payload,
    )
    deps.runtime.worker.queue.enqueue(created_run.id)
    return OperatorFollowUpRunResult(
        source_run_id=source_run.id,
        operator_follow_up=follow_up,
        selected_actions=[action for _, action in selected],
        created_run=created_run,
    )


def _selected_sandbox_operator_actions(
    summary: RunInspectionSummary,
    kind: RunSandboxOperatorActionKind,
) -> list[tuple[RunSandboxDiagnostic, RunSandboxOperatorAction]]:
    selected = [
        (sandbox_run, action)
        for sandbox_run in summary.sandbox_runs
        for action in sandbox_run.operator_actions
        if action.kind == kind
    ]
    if not selected:
        raise HTTPException(status_code=422, detail=f"Unknown operator action kind: {kind}")
    return selected


def _operator_follow_up_options(
    *,
    source_run: AgentRun,
    selected: list[tuple[RunSandboxDiagnostic, RunSandboxOperatorAction]],
) -> AgentRunOperatorFollowUpOptions:
    first = selected[0][1]
    return AgentRunOperatorFollowUpOptions(
        source_run_id=source_run.id,
        action_kind=first.kind,
        action_label=first.label,
        action_reason=_operator_follow_up_reason(selected),
        action_ids=[action.kind for _, action in selected],
        sandbox_run_ids=[sandbox_run.sandbox_run_id for sandbox_run, _ in selected],
        workspace_paths=[
            action.workspace_path
            for _, action in selected
            if action.workspace_path is not None
        ],
        method=first.method,
        path=first.path,
    )


def _operator_follow_up_reason(
    selected: list[tuple[RunSandboxDiagnostic, RunSandboxOperatorAction]],
) -> str:
    reasons = []
    seen: set[str] = set()
    for _, action in selected:
        if action.reason in seen:
            continue
        reasons.append(action.reason)
        seen.add(action.reason)
    return "\n".join(reasons)


def _operator_follow_up_harness_options(
    *,
    source_run: AgentRun,
    follow_up: AgentRunOperatorFollowUpOptions,
    selected: list[tuple[RunSandboxDiagnostic, RunSandboxOperatorAction]],
    extra_instructions: str | None,
) -> AgentRunHarnessOptions:
    inherited = source_run.harness_options
    lines = [
        f"Follow up on operator action {follow_up.action_kind} from source run {source_run.id}.",
        f"Action label: {follow_up.action_label}.",
        "Action reason:",
        follow_up.action_reason,
    ]
    if follow_up.workspace_paths:
        lines.append("Workspace paths: " + ", ".join(follow_up.workspace_paths) + ".")
    lines.append("Selected sandbox runs: " + ", ".join(follow_up.sandbox_run_ids) + ".")
    lines.append("Use the existing workspace and inspect prior run context before changing outputs.")
    lines.append("Do not bypass capability policy; call only allowed tools through the Aithru tool bridge.")
    if inherited and inherited.instructions:
        lines.append("Prior run instructions:")
        lines.append(inherited.instructions)
    if extra_instructions:
        lines.append("Additional operator instructions:")
        lines.append(extra_instructions)
    return AgentRunHarnessOptions(
        model=inherited.model if inherited else None,
        instructions=_bounded_instruction("\n".join(lines)),
        operator_follow_up=follow_up,
    )


def _operator_follow_up_goal(
    source_run: AgentRun,
    follow_up: AgentRunOperatorFollowUpOptions,
) -> str:
    return f"Follow up {follow_up.action_kind} from run {source_run.id}"


def _selected_research_continuation_actions(
    *,
    continuation: ResearchContinuationSnapshot,
    action_ids: list[str] | None,
) -> list[ResearchContinuationAction]:
    actions_by_id = {action.action_id: action for action in continuation.actions}
    if action_ids is None:
        return list(continuation.actions)
    unknown = [action_id for action_id in action_ids if action_id not in actions_by_id]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown research continuation action id: {unknown[0]}",
        )
    return [actions_by_id[action_id] for action_id in action_ids]


def _selected_research_continuation_target_section_ids(
    selected_actions: list[ResearchContinuationAction],
) -> list[str]:
    target_section_ids: list[str] = []
    seen: set[str] = set()
    for action in selected_actions:
        for section_id in action.target_section_ids:
            if section_id in seen:
                continue
            target_section_ids.append(section_id)
            seen.add(section_id)
    return target_section_ids


def _continuation_harness_options(
    *,
    source_run: AgentRun,
    continuation: ResearchContinuationSnapshot,
    selected_actions: list[ResearchContinuationAction],
    action_ids: list[str],
    target_section_ids: list[str],
    extra_instructions: str | None,
) -> AgentRunHarnessOptions:
    inherited = source_run.harness_options
    lines = [
        f"Continue research from source run {source_run.id}.",
        f"Source report status: {continuation.report_status}; continuation status: {continuation.status}.",
    ]
    if continuation.query:
        lines.append(f"Research query: {continuation.query}.")
    lines.append("Selected continuation actions:")
    for action in selected_actions:
        lines.append(_continuation_action_instruction_line(action))
    lines.append("Use the existing workspace and prior cited evidence when useful.")
    lines.append("Do not bypass capability policy; call only allowed tools through the Aithru tool bridge.")
    if inherited and inherited.instructions:
        lines.append("Prior run instructions:")
        lines.append(inherited.instructions)
    if extra_instructions:
        lines.append("Additional continuation instructions:")
        lines.append(extra_instructions)
    return AgentRunHarnessOptions(
        model=inherited.model if inherited else None,
        instructions=_bounded_instruction("\n".join(lines)),
        research_continuation=AgentRunResearchContinuationOptions(
            source_run_id=source_run.id,
            continuation_status=continuation.status,
            query=continuation.query,
            action_ids=action_ids,
            target_section_ids=target_section_ids,
        ),
    )


def _continuation_action_instruction_line(action: ResearchContinuationAction) -> str:
    suffixes = []
    if action.target_section_ids:
        suffixes.append("sections: " + ", ".join(action.target_section_ids))
    if action.suggested_tool_names:
        suffixes.append("tools: " + ", ".join(action.suggested_tool_names))
    if action.suggested_research_phases:
        suffixes.append("phases: " + ", ".join(action.suggested_research_phases))
    suffix = f" ({'; '.join(suffixes)})" if suffixes else ""
    return f"- {action.action_id} [{action.priority}] {action.title}: {action.reason}{suffix}"


def _continuation_goal(
    source_run: AgentRun,
    continuation: ResearchContinuationSnapshot,
) -> str:
    if continuation.query:
        return f"Continue research for: {continuation.query}"
    return f"Continue research from run {source_run.id}"


def _bounded_instruction(value: str, *, max_chars: int = 4_000) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


async def _thread_access_allowed(request: Request, *, thread_id: str, deps: ApiDependencies) -> bool:
    try:
        await deps.require_thread(request, thread_id)
    except HTTPException:
        return False
    return True


async def _run_detail_response(run: AgentRun, deps: ApiDependencies) -> RunDetailResponse:
    summary = await _build_run_inspection_summary_for_run(run, deps)
    return RunDetailResponse.model_validate(
        {
            **dump_model(run),
            "summary": summary,
        }
    )


async def _dump_run_with_summary(run: AgentRun, deps: ApiDependencies) -> RunListItem:
    summary = await _build_run_inspection_summary_for_run(run, deps)
    return RunListItem.model_validate(
        {
            **dump_model(run),
            "summary": summary,
        }
    )


async def _build_run_inspection_summary_for_run(
    run: AgentRun,
    deps: ApiDependencies,
) -> RunInspectionSummary:
    events = await deps.runtime.event_store.list_by_run(run.id)
    trace = project_trace_spans(events)
    todos = await deps.runtime.store.list_todos(run.id)
    artifacts = await deps.runtime.store.list_artifacts(run_id=run.id)
    approvals = [
        approval
        for approval in await deps.runtime.store.list_approvals()
        if approval.run_id == run.id
    ]
    return build_run_inspection_summary(
        run=run,
        events=events,
        todos=todos,
        artifacts=artifacts,
        approvals=approvals,
        trace=trace,
    )


async def _build_run_list_page(
    runs: list[AgentRun],
    query: RunListQuery,
    deps: ApiDependencies,
) -> RunListPage:
    results: list[RunListItem] = []
    for run in runs:
        run_payload = await _dump_run_with_summary(run, deps)
        if _summary_matches_list_query(run_payload.summary, query):
            results.append(run_payload)
    items = _paginate_run_payloads(_sort_run_payloads(results, query), query)
    return RunListPage(
        items=items,
        total=len(results),
        count=len(items),
        limit=query.limit,
        offset=query.offset,
        order_by=query.order_by,
        order_direction=query.order_direction,
        sandbox_operator_action_counts=_sandbox_operator_action_counts(results),
        operator_follow_up_action_counts=_operator_follow_up_action_counts(results),
        operator_follow_up_source_run_counts=_operator_follow_up_source_run_counts(results),
    )


def _dump_run_list_response(
    page: RunListPage,
    query: RunListQuery,
) -> RunListResponse:
    if query.include_meta:
        return page
    return page.items


def _run_matches_list_query(run: AgentRun, query: RunListQuery) -> bool:
    if query.status is not None and run.status != query.status:
        return False
    if query.skill_id is not None and run.skill_id != query.skill_id:
        return False
    follow_up = run.harness_options.operator_follow_up if run.harness_options else None
    if query.operator_follow_up is not None and bool(follow_up) != query.operator_follow_up:
        return False
    if (
        query.operator_follow_up_source_run_id is not None
        and (
            follow_up is None
            or follow_up.source_run_id != query.operator_follow_up_source_run_id
        )
    ):
        return False
    if (
        query.operator_follow_up_action_kind is not None
        and (
            follow_up is None
            or follow_up.action_kind != query.operator_follow_up_action_kind
        )
    ):
        return False
    return True


def _summary_matches_list_query(summary: RunInspectionSummary, query: RunListQuery) -> bool:
    if query.health is not None and summary.health != query.health:
        return False
    if query.needs_attention is not None and summary.needs_attention != query.needs_attention:
        return False
    if (
        query.external_run_stale is not None
        and summary.external_run_stale != query.external_run_stale
    ):
        return False
    if (
        query.sandbox_failed is not None
        and bool(summary.failed_sandbox_run_count) != query.sandbox_failed
    ):
        return False
    if query.sandbox_side_effects is not None:
        has_sandbox_side_effects = (
            summary.sandbox_workspace_file_count > 0
            or summary.sandbox_artifact_promotion_count > 0
        )
        if has_sandbox_side_effects != query.sandbox_side_effects:
            return False
    if query.needs_operator_action is not None:
        has_operator_action = summary.sandbox_operator_action_count > 0
        if has_operator_action != query.needs_operator_action:
            return False
    if (
        query.sandbox_operator_action_kind is not None
        and not _summary_has_sandbox_operator_action_kind(
            summary,
            query.sandbox_operator_action_kind,
        )
    ):
        return False
    return True


def _summary_has_sandbox_operator_action_kind(
    summary: RunInspectionSummary,
    kind: RunSandboxOperatorActionKind,
) -> bool:
    return any(action.kind == kind for action in summary.sandbox_operator_actions)


def _sort_run_payloads(
    run_payloads: list[RunListItem],
    query: RunListQuery,
) -> list[RunListItem]:
    if query.order_by is None:
        return run_payloads
    present: list[tuple[object, RunListItem]] = []
    missing: list[RunListItem] = []
    for run_payload in run_payloads:
        value = _run_order_value(run_payload, query.order_by)
        if value is None:
            missing.append(run_payload)
        else:
            present.append((value, run_payload))
    present.sort(key=lambda item: item[0], reverse=query.order_direction == "desc")
    return [run_payload for _, run_payload in present] + missing


def _run_order_value(run_payload: RunListItem, order_by: RunListOrderBy) -> object | None:
    if order_by == "health":
        return run_payload.summary.health
    if order_by == "sandbox_operator_action_count":
        return run_payload.summary.sandbox_operator_action_count
    value = getattr(run_payload, order_by)
    if isinstance(value, str):
        return value
    return None


def _sandbox_operator_action_counts(
    run_payloads: list[RunListItem],
) -> dict[RunSandboxOperatorActionKind, int]:
    counts: dict[RunSandboxOperatorActionKind, int] = {}
    for run_payload in run_payloads:
        for action in run_payload.summary.sandbox_operator_actions:
            counts[action.kind] = counts.get(action.kind, 0) + 1
    return dict(sorted(counts.items()))


def _operator_follow_up_action_counts(
    run_payloads: list[RunListItem],
) -> dict[RunSandboxOperatorActionKind, int]:
    counts: dict[RunSandboxOperatorActionKind, int] = {}
    for follow_up in _operator_follow_up_payloads(run_payloads):
        counts[follow_up.action_kind] = counts.get(follow_up.action_kind, 0) + 1
    return dict(sorted(counts.items()))


def _operator_follow_up_source_run_counts(
    run_payloads: list[RunListItem],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for follow_up in _operator_follow_up_payloads(run_payloads):
        counts[follow_up.source_run_id] = counts.get(follow_up.source_run_id, 0) + 1
    return dict(sorted(counts.items()))


def _operator_follow_up_payloads(
    run_payloads: list[RunListItem],
) -> list[AgentRunOperatorFollowUpOptions]:
    follow_ups: list[AgentRunOperatorFollowUpOptions] = []
    for run_payload in run_payloads:
        if run_payload.harness_options is None:
            continue
        follow_up = run_payload.harness_options.operator_follow_up
        if follow_up is not None:
            follow_ups.append(follow_up)
    return follow_ups


def _paginate_run_payloads(
    run_payloads: list[RunListItem],
    query: RunListQuery,
) -> list[RunListItem]:
    offset_payloads = run_payloads[query.offset :]
    if query.limit is None:
        return offset_payloads
    return offset_payloads[: query.limit]


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


def _run_live_stream_response(run_id: str, deps: ApiDependencies) -> Response:
    worker_task = asyncio.create_task(deps.runtime.worker.drain(limit=1))

    async def stream_events():
        try:
            async for event in deps.follow_run_events(
                run_id,
                after_sequence=0,
                poll_interval_seconds=0.01,
                timeout_seconds=30.0,
            ):
                yield event
        finally:
            if not worker_task.done():
                await worker_task

    return StreamingResponse(stream_events(), media_type="text/event-stream")


async def _cancel_run(run_id: str, deps: ApiDependencies) -> AgentRun:
    try:
        run = await deps.runtime.runner.cancel_run(run_id)
    except AgentError as err:
        status_code = 404 if err.code == "NOT_FOUND" else 409
        raise HTTPException(status_code=status_code, detail=err.message) from err
    return run
