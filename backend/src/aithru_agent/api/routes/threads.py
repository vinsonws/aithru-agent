"""Agent thread routes."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator

from aithru_agent.api.dependencies import (
    ApiDependencies,
    CreateThreadRequest,
    UpdateThreadRequest,
    api_deps,
    identity_value,
    run_visible,
    thread_visible,
)
from aithru_agent.api.snapshots import (
    ResearchContinuationAction,
    ResearchSnapshotStatus,
    RunInspectionAttentionReason,
    RunInspectionSummary,
    RunResumeSnapshot,
    RunSandboxOperatorAction,
    RunSnapshotResponse,
    build_operator_follow_up_lineage_snapshot,
    build_research_continuation_lineage_snapshot,
    build_research_continuation_snapshot,
    build_research_evidence_ledger,
    build_research_execution_snapshot,
    build_research_review_snapshot,
    build_research_snapshot_summary,
    build_run_inspection_summary,
    build_run_resume_snapshot,
)
from aithru_agent.domain import (
    AgentMessage,
    AgentMessageRole,
    AgentRun,
    AgentRunStatus,
    AgentThread,
    AgentThreadStatus,
)
from aithru_agent.trace import project_trace_spans

router = APIRouter()

ThreadListOrderBy = Literal["created_at", "updated_at", "title", "status"]
ThreadListOrderDirection = Literal["asc", "desc"]
ThreadDashboardOrderBy = Literal[
    "last_activity_at",
    "title",
    "created_at",
    "updated_at",
    "needs_attention",
]
ThreadDashboardOrderDirection = Literal["asc", "desc"]
ThreadDashboardActionKind = Literal[
    "answer_input",
    "review_approval",
    "resolve_external_approval",
    "resolve_external_run",
    "continue_research",
    "follow_up_operator_action",
]
ThreadDashboardActionSource = Literal[
    "resume",
    "research_continuation",
    "sandbox_operator_action",
]
ThreadDashboardActionPriority = Literal["high", "medium", "low"]
ThreadDashboardActionMethod = Literal["GET", "POST"]


class ThreadListQuery(BaseModel):
    status: AgentThreadStatus | None = None
    include_meta: bool = False
    order_by: ThreadListOrderBy | None = None
    order_direction: ThreadListOrderDirection = "asc"
    limit: int | None = Field(default=None, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ThreadListPage(BaseModel):
    items: list[AgentThread]
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int | None = None
    offset: int = Field(ge=0)
    order_by: ThreadListOrderBy | None = None
    order_direction: ThreadListOrderDirection
    status_counts: dict[AgentThreadStatus, int] = Field(default_factory=dict)


ThreadListResponse = list[AgentThread] | ThreadListPage


class ThreadDashboardQuery(BaseModel):
    status: AgentThreadStatus | None = None
    needs_attention: bool | None = None
    research_degraded: bool | None = None
    order_by: ThreadDashboardOrderBy = "last_activity_at"
    order_direction: ThreadDashboardOrderDirection = "desc"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


_THREAD_SUMMARY_PREVIEW_CHARS = 160
_TERMINAL_RUN_STATUSES = {
    AgentRunStatus.COMPLETED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
}


class AgentThreadSummaryMessage(BaseModel):
    message_id: str
    role: AgentMessageRole
    content_preview: str = Field(max_length=_THREAD_SUMMARY_PREVIEW_CHARS)
    truncated: bool
    created_at: str
    run_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class AgentThreadSummaryRun(BaseModel):
    run_id: str
    status: AgentRunStatus
    task_msg: str
    started_at: str
    completed_at: str | None = None


class AgentThreadSummary(BaseModel):
    thread_id: str
    message_count: int = Field(ge=0)
    run_count: int = Field(ge=0)
    active_run_count: int = Field(ge=0)
    waiting_input_run_count: int = Field(ge=0)
    latest_message: AgentThreadSummaryMessage | None = None
    latest_run: AgentThreadSummaryRun | None = None
    last_activity_at: str | None = None


class AgentThreadDashboardActionHint(BaseModel):
    action_id: str = Field(min_length=1)
    kind: ThreadDashboardActionKind
    source: ThreadDashboardActionSource
    priority: ThreadDashboardActionPriority
    label: str = Field(min_length=1)
    reason: str | None = None
    run_id: str = Field(min_length=1)
    method: ThreadDashboardActionMethod | None = None
    path: str | None = None
    thread_path: str | None = None
    related_action_id: str | None = None
    target_section_ids: list[str] = Field(default_factory=list)
    suggested_tool_names: list[str] = Field(default_factory=list)
    workspace_path: str | None = None


class AgentThreadWorkbenchRun(BaseModel):
    run: AgentRun
    summary: RunInspectionSummary
    action_hints: list[AgentThreadDashboardActionHint] = Field(default_factory=list)
    action_count: int = Field(default=0, ge=0)
    high_priority_action_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _action_counts_must_match_hints(self) -> "AgentThreadWorkbenchRun":
        if self.action_count != len(self.action_hints):
            raise ValueError("thread workbench action count must match hints")
        high_priority_count = sum(1 for hint in self.action_hints if hint.priority == "high")
        if self.high_priority_action_count != high_priority_count:
            raise ValueError("thread workbench high-priority count must match hints")
        return self


class AgentThreadWorkbench(BaseModel):
    thread: AgentThread
    summary: AgentThreadSummary
    runs: list[AgentThreadWorkbenchRun] = Field(default_factory=list)
    selected_run_id: str | None = None
    selected_run: RunSnapshotResponse | None = None

    @model_validator(mode="after")
    def _references_must_match_thread(self) -> "AgentThreadWorkbench":
        if self.summary.thread_id != self.thread.id:
            raise ValueError("thread workbench summary must match thread")
        for item in self.runs:
            if item.run.thread_id != self.thread.id:
                raise ValueError("thread workbench run cards must match thread")
        if self.selected_run is None:
            if self.selected_run_id is not None:
                raise ValueError("selected_run_id requires selected_run")
            return self
        if self.selected_run.run.thread_id != self.thread.id:
            raise ValueError("selected run must match thread")
        if self.selected_run_id != self.selected_run.run.id:
            raise ValueError("selected_run_id must match selected run")
        return self


class AgentThreadDashboardItem(BaseModel):
    thread: AgentThread
    summary: AgentThreadSummary
    latest_run: AgentThreadWorkbenchRun | None = None
    needs_attention: bool = False
    attention_reasons: list[RunInspectionAttentionReason] = Field(default_factory=list)
    research_status: ResearchSnapshotStatus = "none"
    research_degraded: bool = False
    last_activity_at: str | None = None
    action_hints: list[AgentThreadDashboardActionHint] = Field(default_factory=list)
    action_count: int = Field(default=0, ge=0)
    high_priority_action_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _dashboard_row_must_match_sources(self) -> "AgentThreadDashboardItem":
        if self.summary.thread_id != self.thread.id:
            raise ValueError("thread dashboard summary must match thread")
        if self.last_activity_at != self.summary.last_activity_at:
            raise ValueError("thread dashboard activity must match summary")
        if self.action_count != len(self.action_hints):
            raise ValueError("thread dashboard action count must match hints")
        high_priority_count = sum(1 for hint in self.action_hints if hint.priority == "high")
        if self.high_priority_action_count != high_priority_count:
            raise ValueError("thread dashboard high-priority count must match hints")
        if self.latest_run is None:
            if self.action_hints:
                raise ValueError("thread dashboard action hints require latest_run")
            if self.needs_attention:
                raise ValueError("thread dashboard needs_attention requires latest_run")
            if self.attention_reasons:
                raise ValueError("thread dashboard attention reasons require latest_run")
            if self.research_status != "none":
                raise ValueError("thread dashboard research status requires latest_run")
            if self.research_degraded:
                raise ValueError("thread dashboard degraded research requires latest_run")
            return self
        if self.latest_run.run.thread_id != self.thread.id:
            raise ValueError("thread dashboard latest run must match thread")
        run_summary = self.latest_run.summary
        if self.needs_attention != run_summary.needs_attention:
            raise ValueError("thread dashboard attention flag must match latest run")
        if self.attention_reasons != run_summary.attention_reasons:
            raise ValueError("thread dashboard attention reasons must match latest run")
        if self.research_status != run_summary.research_status:
            raise ValueError("thread dashboard research status must match latest run")
        if self.research_degraded != run_summary.research_degraded:
            raise ValueError("thread dashboard degraded flag must match latest run")
        return self


class AgentThreadDashboardPage(BaseModel):
    items: list[AgentThreadDashboardItem] = Field(default_factory=list)
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    order_by: ThreadDashboardOrderBy
    order_direction: ThreadDashboardOrderDirection
    status_counts: dict[AgentThreadStatus, int] = Field(default_factory=dict)
    needs_attention_count: int = Field(ge=0)
    research_degraded_count: int = Field(ge=0)
    action_hint_count: int = Field(default=0, ge=0)
    high_priority_action_hint_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _count_must_match_items(self) -> "AgentThreadDashboardPage":
        if self.count != len(self.items):
            raise ValueError("thread dashboard count must match items")
        visible_action_count = sum(item.action_count for item in self.items)
        if self.action_hint_count < visible_action_count:
            raise ValueError("thread dashboard action count must cover page items")
        visible_high_priority_count = sum(
            item.high_priority_action_count for item in self.items
        )
        if self.high_priority_action_hint_count < visible_high_priority_count:
            raise ValueError(
                "thread dashboard high-priority action count must cover page items"
            )
        return self


@router.post("/api/threads", status_code=201, response_model=AgentThread)
async def create_thread(
    request: Request,
    body: CreateThreadRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentThread:
    org_id = identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
    owner_user_id = identity_value(
        request,
        body,
        "owner_user_id",
        body.owner_user_id,
        "x-aithru-user-id",
    )
    thread = await deps.runtime.store.create_thread(
        org_id=org_id,
        owner_user_id=owner_user_id,
        title=body.title,
    )
    return thread


@router.get("/api/threads", response_model=ThreadListResponse)
async def list_threads(
    request: Request,
    query: ThreadListQuery = Depends(),
    deps: ApiDependencies = Depends(api_deps),
) -> ThreadListResponse:
    visible_threads = [
        thread
        for thread in await deps.runtime.store.list_threads()
        if thread_visible(request, thread)
    ]
    status_counts = _thread_status_counts(visible_threads)
    filtered_threads = [
        thread
        for thread in visible_threads
        if query.status is None or thread.status == query.status
    ]
    items = _paginate_threads(_sort_threads(filtered_threads, query), query)
    if query.include_meta:
        return ThreadListPage(
            items=items,
            total=len(filtered_threads),
            count=len(items),
            limit=query.limit,
            offset=query.offset,
            order_by=query.order_by,
            order_direction=query.order_direction,
            status_counts=status_counts,
        )
    return items


@router.get("/api/threads/dashboard", response_model=AgentThreadDashboardPage)
async def get_thread_dashboard(
    request: Request,
    query: ThreadDashboardQuery = Depends(),
    deps: ApiDependencies = Depends(api_deps),
) -> AgentThreadDashboardPage:
    visible_threads = [
        thread
        for thread in await deps.runtime.store.list_threads()
        if thread_visible(request, thread)
    ]
    status_counts = _thread_status_counts(visible_threads)
    runs_by_thread = _runs_by_thread_id(
        _thread_runs_newest_first(
            [
                run
                for run in await deps.runtime.store.list_runs()
                if run.thread_id is not None and run_visible(request, run)
            ]
        )
    )
    candidate_threads = [
        thread
        for thread in visible_threads
        if query.status is None or thread.status == query.status
    ]
    candidate_items = [
        await _build_thread_dashboard_item(
            thread=thread,
            runs=runs_by_thread.get(thread.id, []),
            deps=deps,
        )
        for thread in candidate_threads
    ]
    needs_attention_count = sum(1 for item in candidate_items if item.needs_attention)
    research_degraded_count = sum(1 for item in candidate_items if item.research_degraded)
    filtered_items = [
        item
        for item in candidate_items
        if (
            (query.needs_attention is None or item.needs_attention == query.needs_attention)
            and (
                query.research_degraded is None
                or item.research_degraded == query.research_degraded
            )
        )
    ]
    items = _paginate_thread_dashboard_items(
        _sort_thread_dashboard_items(filtered_items, query),
        query,
    )
    action_hint_count = sum(item.action_count for item in filtered_items)
    high_priority_action_hint_count = sum(
        item.high_priority_action_count for item in filtered_items
    )
    return AgentThreadDashboardPage(
        items=items,
        total=len(filtered_items),
        count=len(items),
        limit=query.limit,
        offset=query.offset,
        order_by=query.order_by,
        order_direction=query.order_direction,
        status_counts=status_counts,
        needs_attention_count=needs_attention_count,
        research_degraded_count=research_degraded_count,
        action_hint_count=action_hint_count,
        high_priority_action_hint_count=high_priority_action_hint_count,
    )


@router.get("/api/threads/{thread_id}", response_model=AgentThread)
async def get_thread(
    request: Request,
    thread_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentThread:
    thread = await deps.require_thread(request, thread_id)
    return thread


@router.get("/api/threads/{thread_id}/summary", response_model=AgentThreadSummary)
async def get_thread_summary(
    request: Request,
    thread_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentThreadSummary:
    thread = await deps.require_thread(request, thread_id)
    messages = await deps.runtime.store.list_messages(thread_id)
    runs = [
        run
        for run in await deps.runtime.store.list_runs()
        if run.thread_id == thread_id and run_visible(request, run)
    ]
    return _build_thread_summary(thread=thread, messages=messages, runs=runs)


@router.get("/api/threads/{thread_id}/workbench", response_model=AgentThreadWorkbench)
async def get_thread_workbench(
    request: Request,
    thread_id: str,
    selected_run_id: str | None = None,
    run_limit: int = Query(default=20, ge=1, le=100),
    deps: ApiDependencies = Depends(api_deps),
) -> AgentThreadWorkbench:
    thread = await deps.require_thread(request, thread_id)
    messages = await deps.runtime.store.list_messages(thread_id)
    visible_runs = _thread_runs_newest_first(
        [
            run
            for run in await deps.runtime.store.list_runs()
            if run.thread_id == thread_id and run_visible(request, run)
        ]
    )
    selected_run = await _selected_thread_workbench_run(
        request=request,
        thread_id=thread_id,
        selected_run_id=selected_run_id,
        visible_runs=visible_runs,
        deps=deps,
    )
    return AgentThreadWorkbench(
        thread=thread,
        summary=_build_thread_summary(thread=thread, messages=messages, runs=visible_runs),
        runs=[
            await _build_thread_workbench_run(run=run, deps=deps)
            for run in visible_runs[:run_limit]
        ],
        selected_run_id=selected_run.id if selected_run is not None else None,
        selected_run=(
            await _build_run_snapshot_response(selected_run, deps)
            if selected_run is not None
            else None
        ),
    )


@router.patch("/api/threads/{thread_id}", response_model=AgentThread)
async def update_thread(
    request: Request,
    thread_id: str,
    body: UpdateThreadRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentThread:
    await deps.require_thread(request, thread_id)
    return await deps.runtime.store.update_thread(thread_id, **body.store_updates())


def _thread_status_counts(threads: list[AgentThread]) -> dict[AgentThreadStatus, int]:
    counts: dict[AgentThreadStatus, int] = {}
    for thread in threads:
        counts[thread.status] = counts.get(thread.status, 0) + 1
    return dict(sorted(counts.items()))


def _sort_threads(threads: list[AgentThread], query: ThreadListQuery) -> list[AgentThread]:
    if query.order_by is None:
        return threads
    return sorted(
        threads,
        key=lambda thread: _thread_order_value(thread, query.order_by),
        reverse=query.order_direction == "desc",
    )


def _thread_order_value(thread: AgentThread, order_by: ThreadListOrderBy) -> str:
    value = getattr(thread, order_by)
    if value is None:
        return ""
    return str(value)


def _paginate_threads(threads: list[AgentThread], query: ThreadListQuery) -> list[AgentThread]:
    offset_threads = threads[query.offset :]
    if query.limit is None:
        return offset_threads
    return offset_threads[: query.limit]


def _runs_by_thread_id(runs: list[AgentRun]) -> dict[str, list[AgentRun]]:
    runs_by_thread: dict[str, list[AgentRun]] = {}
    for run in runs:
        if run.thread_id is not None:
            runs_by_thread.setdefault(run.thread_id, []).append(run)
    return runs_by_thread


def _sort_thread_dashboard_items(
    items: list[AgentThreadDashboardItem],
    query: ThreadDashboardQuery,
) -> list[AgentThreadDashboardItem]:
    return sorted(
        items,
        key=lambda item: _thread_dashboard_order_value(item, query.order_by),
        reverse=query.order_direction == "desc",
    )


def _thread_dashboard_order_value(
    item: AgentThreadDashboardItem,
    order_by: ThreadDashboardOrderBy,
) -> str | bool:
    if order_by == "last_activity_at":
        return item.last_activity_at or ""
    if order_by == "needs_attention":
        return item.needs_attention
    return _thread_order_value(item.thread, order_by)


def _paginate_thread_dashboard_items(
    items: list[AgentThreadDashboardItem],
    query: ThreadDashboardQuery,
) -> list[AgentThreadDashboardItem]:
    offset_items = items[query.offset :]
    return offset_items[: query.limit]


async def _build_thread_dashboard_item(
    *,
    thread: AgentThread,
    runs: list[AgentRun],
    deps: ApiDependencies,
) -> AgentThreadDashboardItem:
    messages = await deps.runtime.store.list_messages(thread.id)
    summary = _build_thread_summary(thread=thread, messages=messages, runs=runs)
    latest_run = runs[0] if runs else None
    latest_run_card = (
        await _build_thread_workbench_run(run=latest_run, deps=deps)
        if latest_run is not None
        else None
    )
    run_summary = latest_run_card.summary if latest_run_card is not None else None
    action_hints = latest_run_card.action_hints if latest_run_card is not None else []
    return AgentThreadDashboardItem(
        thread=thread,
        summary=summary,
        latest_run=latest_run_card,
        needs_attention=run_summary.needs_attention if run_summary is not None else False,
        attention_reasons=run_summary.attention_reasons if run_summary is not None else [],
        research_status=run_summary.research_status if run_summary is not None else "none",
        research_degraded=run_summary.research_degraded if run_summary is not None else False,
        last_activity_at=summary.last_activity_at,
        action_hints=action_hints,
        action_count=len(action_hints),
        high_priority_action_count=sum(1 for hint in action_hints if hint.priority == "high"),
    )


async def _build_thread_workbench_run(
    *,
    run: AgentRun,
    deps: ApiDependencies,
) -> AgentThreadWorkbenchRun:
    summary = await _build_run_inspection_summary_for_run(run, deps)
    action_hints = await _build_thread_dashboard_action_hints(
        run=run,
        summary=summary,
        deps=deps,
    )
    return AgentThreadWorkbenchRun(
        run=run,
        summary=summary,
        action_hints=action_hints,
        action_count=len(action_hints),
        high_priority_action_count=sum(1 for hint in action_hints if hint.priority == "high"),
    )


async def _build_thread_dashboard_action_hints(
    *,
    run: AgentRun,
    summary: RunInspectionSummary,
    deps: ApiDependencies,
) -> list[AgentThreadDashboardActionHint]:
    events = await deps.runtime.event_store.list_by_run(run.id)
    trace = project_trace_spans(events)
    todos = await deps.runtime.store.list_todos(run.id)
    artifacts = await deps.runtime.store.list_artifacts(run_id=run.id)
    approvals = [
        approval
        for approval in await deps.runtime.store.list_approvals()
        if approval.run_id == run.id
    ]
    subagents = await deps.runtime.store.list_subagent_runs(parent_run_id=run.id)
    resume = build_run_resume_snapshot(
        run=run,
        events=events,
        approvals=approvals,
        subagents=subagents,
    )
    hints = _resume_dashboard_action_hints(run=run, resume=resume)
    if summary.research_degraded:
        continuation = build_research_continuation_snapshot(
            run=run,
            events=events,
            todos=todos,
            artifacts=artifacts,
            trace=trace,
        )
        hints.extend(
            _research_dashboard_action_hint(run=run, action=action)
            for action in continuation.actions
        )
    hints.extend(
        _sandbox_dashboard_action_hint(run=run, action=action, index=index)
        for index, action in enumerate(summary.sandbox_operator_actions)
    )
    return sorted(hints, key=_thread_dashboard_action_sort_key)


def _resume_dashboard_action_hints(
    *,
    run: AgentRun,
    resume: RunResumeSnapshot,
) -> list[AgentThreadDashboardActionHint]:
    if not resume.resumable:
        return []
    if resume.kind == "input":
        input_request_id = resume.input_request_id or "current"
        return [
            AgentThreadDashboardActionHint(
                action_id=f"{run.id}:resume:input:{input_request_id}",
                kind="answer_input",
                source="resume",
                priority="high",
                label="Answer input request",
                reason=resume.input_prompt or resume.reason,
                run_id=run.id,
                method="POST",
                path=f"/api/runs/{run.id}/input",
                thread_path=_thread_run_action_path(run, "input"),
                related_action_id=resume.input_request_id,
            )
        ]
    if resume.kind == "approval":
        approval_id = resume.approval_id or "current"
        return [
            AgentThreadDashboardActionHint(
                action_id=f"{run.id}:resume:approval:{approval_id}",
                kind="review_approval",
                source="resume",
                priority="high",
                label="Review approval request",
                reason=resume.reason,
                run_id=run.id,
                method="GET",
                path=f"/api/approvals/{approval_id}",
                related_action_id=resume.approval_id,
            )
        ]
    if resume.kind == "external_approval":
        approval_id = resume.external_approval_id or resume.approval_id or "current"
        return [
            AgentThreadDashboardActionHint(
                action_id=f"{run.id}:resume:external_approval:{approval_id}",
                kind="resolve_external_approval",
                source="resume",
                priority="high",
                label="Resolve external approval",
                reason=resume.reason,
                run_id=run.id,
                method="POST",
                path=f"/api/runs/{run.id}/external-approval/resolve",
                related_action_id=resume.external_approval_id or resume.approval_id,
            )
        ]
    if resume.kind == "external_run":
        capability_run_id = resume.external_capability_run_id or "current"
        return [
            AgentThreadDashboardActionHint(
                action_id=f"{run.id}:resume:external_run:{capability_run_id}",
                kind="resolve_external_run",
                source="resume",
                priority="medium",
                label="Resolve external run",
                reason=resume.reason,
                run_id=run.id,
                method="POST",
                path=f"/api/runs/{run.id}/external-run/resolve",
                related_action_id=resume.external_capability_run_id,
            )
        ]
    return []


def _research_dashboard_action_hint(
    *,
    run: AgentRun,
    action: ResearchContinuationAction,
) -> AgentThreadDashboardActionHint:
    return AgentThreadDashboardActionHint(
        action_id=f"{run.id}:research:{action.action_id}",
        kind="continue_research",
        source="research_continuation",
        priority=action.priority,
        label=action.title,
        reason=action.reason,
        run_id=run.id,
        method="POST",
        path=f"/api/runs/{run.id}/research/continue",
        thread_path=_thread_run_action_path(run, "research/continue"),
        related_action_id=action.action_id,
        target_section_ids=action.target_section_ids,
        suggested_tool_names=action.suggested_tool_names,
    )


def _sandbox_dashboard_action_hint(
    *,
    run: AgentRun,
    action: RunSandboxOperatorAction,
    index: int,
) -> AgentThreadDashboardActionHint:
    return AgentThreadDashboardActionHint(
        action_id=f"{run.id}:sandbox:{index}:{action.kind}",
        kind="follow_up_operator_action",
        source="sandbox_operator_action",
        priority=_sandbox_dashboard_action_priority(action),
        label=action.label,
        reason=action.reason,
        run_id=run.id,
        method="POST",
        path=f"/api/runs/{run.id}/operator-actions/follow-up",
        thread_path=_thread_run_action_path(run, "operator-actions/follow-up"),
        related_action_id=action.kind,
        workspace_path=action.workspace_path,
    )


def _sandbox_dashboard_action_priority(
    action: RunSandboxOperatorAction,
) -> ThreadDashboardActionPriority:
    if action.kind in {"inspect_sandbox_error", "retry_sandbox_run"}:
        return "high"
    return "medium"


def _thread_dashboard_action_sort_key(
    hint: AgentThreadDashboardActionHint,
) -> tuple[int, int, str]:
    priority_order = {"high": 0, "medium": 1, "low": 2}
    source_order = {"resume": 0, "research_continuation": 1, "sandbox_operator_action": 2}
    return (
        priority_order[hint.priority],
        source_order[hint.source],
        hint.action_id,
    )


def _thread_run_action_path(run: AgentRun, suffix: str) -> str | None:
    if run.thread_id is None:
        return None
    return f"/api/threads/{run.thread_id}/runs/{run.id}/{suffix}"


def _build_thread_summary(
    *,
    thread: AgentThread,
    messages: list[AgentMessage],
    runs: list[AgentRun],
) -> AgentThreadSummary:
    latest_message = _latest_message(messages)
    latest_run = _latest_run(runs)
    active_run_count = sum(1 for run in runs if run.status not in _TERMINAL_RUN_STATUSES)
    waiting_input_run_count = sum(1 for run in runs if run.status == AgentRunStatus.WAITING_INPUT)
    activity_candidates = [thread.updated_at]
    activity_candidates.extend(message.created_at for message in messages)
    activity_candidates.extend(run.completed_at or run.started_at for run in runs)
    return AgentThreadSummary(
        thread_id=thread.id,
        message_count=len(messages),
        run_count=len(runs),
        active_run_count=active_run_count,
        waiting_input_run_count=waiting_input_run_count,
        latest_message=_message_summary(latest_message) if latest_message is not None else None,
        latest_run=_run_summary(latest_run) if latest_run is not None else None,
        last_activity_at=max(activity_candidates) if activity_candidates else None,
    )


def _latest_message(messages: list[AgentMessage]) -> AgentMessage | None:
    if not messages:
        return None
    return max(messages, key=lambda message: message.created_at)


def _latest_run(runs: list[AgentRun]) -> AgentRun | None:
    if not runs:
        return None
    return max(runs, key=lambda run: run.completed_at or run.started_at)


def _thread_runs_newest_first(runs: list[AgentRun]) -> list[AgentRun]:
    return sorted(runs, key=lambda run: run.completed_at or run.started_at, reverse=True)


async def _selected_thread_workbench_run(
    *,
    request: Request,
    thread_id: str,
    selected_run_id: str | None,
    visible_runs: list[AgentRun],
    deps: ApiDependencies,
) -> AgentRun | None:
    if selected_run_id is None:
        return visible_runs[0] if visible_runs else None
    return await deps.require_thread_run(request, thread_id, selected_run_id)


def _message_summary(message: AgentMessage) -> AgentThreadSummaryMessage:
    content_preview = message.content[:_THREAD_SUMMARY_PREVIEW_CHARS]
    return AgentThreadSummaryMessage(
        message_id=message.id,
        role=message.role,
        content_preview=content_preview,
        truncated=len(message.content) > _THREAD_SUMMARY_PREVIEW_CHARS,
        created_at=message.created_at,
        run_id=message.run_id,
        artifact_ids=message.artifact_ids,
    )


def _run_summary(run: AgentRun) -> AgentThreadSummaryRun:
    return AgentThreadSummaryRun(
        run_id=run.id,
        status=run.status,
        task_msg=run.task_msg,
        started_at=run.started_at,
        completed_at=run.completed_at,
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


async def _build_run_snapshot_response(
    run: AgentRun,
    deps: ApiDependencies,
) -> RunSnapshotResponse:
    events = await deps.runtime.event_store.list_by_run(run.id)
    trace = project_trace_spans(events)
    todos = await deps.runtime.store.list_todos(run.id)
    artifacts = await deps.runtime.store.list_artifacts(run_id=run.id)
    approvals = [
        approval
        for approval in await deps.runtime.store.list_approvals()
        if approval.run_id == run.id
    ]
    subagents = await deps.runtime.store.list_subagent_runs(parent_run_id=run.id)
    runs_by_id = {item.id: item for item in await deps.runtime.store.list_runs()}
    return RunSnapshotResponse(
        run=run,
        summary=build_run_inspection_summary(
            run=run,
            events=events,
            todos=todos,
            artifacts=artifacts,
            approvals=approvals,
            trace=trace,
        ),
        events=events,
        trace=trace,
        todos=todos,
        approvals=approvals,
        workspace_files=await deps.runtime.store.list_workspace_files(run.workspace_id),
        artifacts=artifacts,
        research=build_research_snapshot_summary(
            events=events,
            todos=todos,
            artifacts=artifacts,
            trace=trace,
        ),
        research_execution=build_research_execution_snapshot(
            run=run,
            events=events,
            todos=todos,
            artifacts=artifacts,
            trace=trace,
        ),
        research_evidence=build_research_evidence_ledger(
            run=run,
            events=events,
            artifacts=artifacts,
        ),
        research_review=build_research_review_snapshot(
            run=run,
            events=events,
            todos=todos,
            artifacts=artifacts,
            trace=trace,
        ),
        research_continuation=build_research_continuation_snapshot(
            run=run,
            events=events,
            todos=todos,
            artifacts=artifacts,
            trace=trace,
        ),
        research_lineage=build_research_continuation_lineage_snapshot(
            run=run,
            events=events,
            runs_by_id=runs_by_id,
        ),
        operator_follow_up_lineage=build_operator_follow_up_lineage_snapshot(
            run=run,
            events=events,
            runs_by_id=runs_by_id,
        ),
        resume=build_run_resume_snapshot(
            run=run,
            events=events,
            approvals=approvals,
            subagents=subagents,
        ),
        subagents=subagents,
    )
