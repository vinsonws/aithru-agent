"""Agent run event, trace, and snapshot routes."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    CreateRunExportArtifactRequest,
    api_deps,
    dump_model,
)
from aithru_agent.api.snapshots import (
    OperatorFollowUpLineageSnapshot,
    ResearchContinuationLineageSnapshot,
    ResearchContinuationSnapshot,
    ResearchEvidenceLedger,
    ResearchExecutionSnapshot,
    ResearchReviewSnapshot,
    RunTreeSnapshot,
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
    build_run_tree_snapshot,
)
from aithru_agent.domain import (
    AgentCapabilityAuditEvent,
    AgentCapabilityAuditLog,
    AgentCapabilityAuditLogEntry,
    AgentRun,
    AgentRunExportArtifactResult,
    AgentRunExportBundle,
    AgentRunExportSummary,
)
from aithru_agent.stream import AgentStreamEvent
from aithru_agent.trace import AgentTraceSpan, project_trace_spans

router = APIRouter()


@router.get("/api/runs/{run_id}/events", response_model=list[AgentStreamEvent])
async def get_run_events(
    request: Request,
    run_id: str,
    after_sequence: int = 0,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentStreamEvent]:
    await deps.require_run(request, run_id)
    return await deps.runtime.event_store.list_after_sequence(run_id, after_sequence)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/events",
    response_model=list[AgentStreamEvent],
)
async def get_thread_run_events(
    request: Request,
    thread_id: str,
    run_id: str,
    after_sequence: int = 0,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentStreamEvent]:
    await deps.require_thread_run(request, thread_id, run_id)
    return await deps.runtime.event_store.list_after_sequence(run_id, after_sequence)


@router.get("/api/runs/{run_id}/capability-audit", response_model=AgentCapabilityAuditLog)
async def get_run_capability_audit(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentCapabilityAuditLog:
    await deps.require_run(request, run_id)
    return await _capability_audit_response(run_id, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/capability-audit",
    response_model=AgentCapabilityAuditLog,
)
async def get_thread_run_capability_audit(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentCapabilityAuditLog:
    await deps.require_thread_run(request, thread_id, run_id)
    return await _capability_audit_response(run_id, deps)


@router.get("/api/runs/{run_id}/trace", response_model=list[AgentTraceSpan])
async def get_run_trace(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentTraceSpan]:
    await deps.require_run(request, run_id)
    events = await deps.runtime.event_store.list_by_run(run_id)
    return project_trace_spans(events)


@router.get("/api/runs/{run_id}/snapshot", response_model=RunSnapshotResponse)
async def get_run_snapshot(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> RunSnapshotResponse:
    run = await deps.require_run(request, run_id)
    events = await deps.runtime.event_store.list_by_run(run_id)
    trace = project_trace_spans(events)
    todos = await deps.runtime.store.list_todos(run_id)
    artifacts = await deps.runtime.store.list_artifacts(run_id=run_id)
    approvals = [
        approval
        for approval in await deps.runtime.store.list_approvals()
        if approval.run_id == run_id
    ]
    subagents = await deps.runtime.store.list_subagent_runs(parent_run_id=run_id)
    runs_by_id = {item.id: item for item in await deps.runtime.store.list_runs()}
    summary = build_run_inspection_summary(
        run=run,
        events=events,
        todos=todos,
        artifacts=artifacts,
        approvals=approvals,
        trace=trace,
    )
    return RunSnapshotResponse(
        run=run,
        summary=summary,
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


@router.get(
    "/api/runs/{run_id}/research/execution",
    response_model=ResearchExecutionSnapshot,
)
async def get_run_research_execution(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchExecutionSnapshot:
    run = await deps.require_run(request, run_id)
    return await _research_execution_response(run, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/research/execution",
    response_model=ResearchExecutionSnapshot,
)
async def get_thread_run_research_execution(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchExecutionSnapshot:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _research_execution_response(run, deps)


@router.get(
    "/api/runs/{run_id}/research/evidence",
    response_model=ResearchEvidenceLedger,
)
async def get_run_research_evidence(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchEvidenceLedger:
    run = await deps.require_run(request, run_id)
    return await _research_evidence_response(run, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/research/evidence",
    response_model=ResearchEvidenceLedger,
)
async def get_thread_run_research_evidence(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchEvidenceLedger:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _research_evidence_response(run, deps)


@router.get(
    "/api/runs/{run_id}/research/review",
    response_model=ResearchReviewSnapshot,
)
async def get_run_research_review(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchReviewSnapshot:
    run = await deps.require_run(request, run_id)
    return await _research_review_response(run, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/research/review",
    response_model=ResearchReviewSnapshot,
)
async def get_thread_run_research_review(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchReviewSnapshot:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _research_review_response(run, deps)


@router.get(
    "/api/runs/{run_id}/research/continuation",
    response_model=ResearchContinuationSnapshot,
)
async def get_run_research_continuation(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchContinuationSnapshot:
    run = await deps.require_run(request, run_id)
    return await _research_continuation_response(run, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/research/continuation",
    response_model=ResearchContinuationSnapshot,
)
async def get_thread_run_research_continuation(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchContinuationSnapshot:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _research_continuation_response(run, deps)


@router.get(
    "/api/runs/{run_id}/research/lineage",
    response_model=ResearchContinuationLineageSnapshot,
)
async def get_run_research_lineage(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchContinuationLineageSnapshot:
    run = await deps.require_run(request, run_id)
    return await _research_lineage_response(run, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/research/lineage",
    response_model=ResearchContinuationLineageSnapshot,
)
async def get_thread_run_research_lineage(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> ResearchContinuationLineageSnapshot:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _research_lineage_response(run, deps)


@router.get(
    "/api/runs/{run_id}/operator-actions/lineage",
    response_model=OperatorFollowUpLineageSnapshot,
)
async def get_run_operator_action_lineage(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> OperatorFollowUpLineageSnapshot:
    run = await deps.require_run(request, run_id)
    return await _operator_follow_up_lineage_response(run, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/operator-actions/lineage",
    response_model=OperatorFollowUpLineageSnapshot,
)
async def get_thread_run_operator_action_lineage(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> OperatorFollowUpLineageSnapshot:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _operator_follow_up_lineage_response(run, deps)


@router.get("/api/runs/{run_id}/export", response_model=AgentRunExportBundle)
async def get_run_export(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRunExportBundle:
    run = await deps.require_run(request, run_id)
    return await _run_export_response(run, deps)


@router.post(
    "/api/runs/{run_id}/export/artifact",
    status_code=201,
    response_model=AgentRunExportArtifactResult,
)
async def create_run_export_artifact(
    request: Request,
    run_id: str,
    body: CreateRunExportArtifactRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRunExportArtifactResult:
    run = await deps.require_run(request, run_id)
    return await _run_export_artifact_response(run, body, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/export",
    response_model=AgentRunExportBundle,
)
async def get_thread_run_export(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRunExportBundle:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _run_export_response(run, deps)


@router.post(
    "/api/threads/{thread_id}/runs/{run_id}/export/artifact",
    status_code=201,
    response_model=AgentRunExportArtifactResult,
)
async def create_thread_run_export_artifact(
    request: Request,
    thread_id: str,
    run_id: str,
    body: CreateRunExportArtifactRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRunExportArtifactResult:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _run_export_artifact_response(run, body, deps)


@router.get("/api/runs/{run_id}/tree", response_model=RunTreeSnapshot)
async def get_run_tree(
    request: Request,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> RunTreeSnapshot:
    run = await deps.require_run(request, run_id)
    return await _run_tree_response(run.id, deps)


@router.get(
    "/api/threads/{thread_id}/runs/{run_id}/tree",
    response_model=RunTreeSnapshot,
)
async def get_thread_run_tree(
    request: Request,
    thread_id: str,
    run_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> RunTreeSnapshot:
    run = await deps.require_thread_run(request, thread_id, run_id)
    return await _run_tree_response(run.id, deps)


async def _run_export_response(run: AgentRun, deps: ApiDependencies) -> AgentRunExportBundle:
    return await _build_run_export_bundle(run, deps)


async def _capability_audit_response(run_id: str, deps: ApiDependencies) -> AgentCapabilityAuditLog:
    events = await deps.runtime.event_store.list_by_run(run_id)
    entries: list[AgentCapabilityAuditLogEntry] = []
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        audit_payload = payload.get("audit")
        if not isinstance(audit_payload, dict):
            continue
        entries.append(
            AgentCapabilityAuditLogEntry(
                source_event_id=event.id,
                source_event_type=event.type,
                sequence=event.sequence,
                audit=AgentCapabilityAuditEvent.model_validate(audit_payload),
            )
        )
    return AgentCapabilityAuditLog(
        run_id=run_id,
        entries=entries,
        count=len(entries),
    )


async def _research_execution_response(
    run: AgentRun,
    deps: ApiDependencies,
) -> ResearchExecutionSnapshot:
    events = await deps.runtime.event_store.list_by_run(run.id)
    trace = project_trace_spans(events)
    todos = await deps.runtime.store.list_todos(run.id)
    artifacts = await deps.runtime.store.list_artifacts(run_id=run.id)
    return build_research_execution_snapshot(
        run=run,
        events=events,
        todos=todos,
        artifacts=artifacts,
        trace=trace,
    )


async def _research_evidence_response(
    run: AgentRun,
    deps: ApiDependencies,
) -> ResearchEvidenceLedger:
    events = await deps.runtime.event_store.list_by_run(run.id)
    artifacts = await deps.runtime.store.list_artifacts(run_id=run.id)
    return build_research_evidence_ledger(
        run=run,
        events=events,
        artifacts=artifacts,
    )


async def _research_review_response(
    run: AgentRun,
    deps: ApiDependencies,
) -> ResearchReviewSnapshot:
    events = await deps.runtime.event_store.list_by_run(run.id)
    trace = project_trace_spans(events)
    todos = await deps.runtime.store.list_todos(run.id)
    artifacts = await deps.runtime.store.list_artifacts(run_id=run.id)
    return build_research_review_snapshot(
        run=run,
        events=events,
        todos=todos,
        artifacts=artifacts,
        trace=trace,
    )


async def _research_continuation_response(
    run: AgentRun,
    deps: ApiDependencies,
) -> ResearchContinuationSnapshot:
    events = await deps.runtime.event_store.list_by_run(run.id)
    trace = project_trace_spans(events)
    todos = await deps.runtime.store.list_todos(run.id)
    artifacts = await deps.runtime.store.list_artifacts(run_id=run.id)
    return build_research_continuation_snapshot(
        run=run,
        events=events,
        todos=todos,
        artifacts=artifacts,
        trace=trace,
    )


async def _research_lineage_response(
    run: AgentRun,
    deps: ApiDependencies,
) -> ResearchContinuationLineageSnapshot:
    events = await deps.runtime.event_store.list_by_run(run.id)
    runs_by_id = {item.id: item for item in await deps.runtime.store.list_runs()}
    return build_research_continuation_lineage_snapshot(
        run=run,
        events=events,
        runs_by_id=runs_by_id,
    )


async def _operator_follow_up_lineage_response(
    run: AgentRun,
    deps: ApiDependencies,
) -> OperatorFollowUpLineageSnapshot:
    events = await deps.runtime.event_store.list_by_run(run.id)
    runs_by_id = {item.id: item for item in await deps.runtime.store.list_runs()}
    return build_operator_follow_up_lineage_snapshot(
        run=run,
        events=events,
        runs_by_id=runs_by_id,
    )


async def _build_run_export_bundle(
    run: AgentRun,
    deps: ApiDependencies,
) -> AgentRunExportBundle:
    events = await deps.runtime.event_store.list_by_run(run.id)
    trace = project_trace_spans(events)
    todos = await deps.runtime.store.list_todos(run.id)
    approvals = [
        approval
        for approval in await deps.runtime.store.list_approvals()
        if approval.run_id == run.id
    ]
    artifacts = await deps.runtime.store.list_artifacts(run_id=run.id)
    workspace_snapshot = await deps.runtime.store.get_workspace_snapshot(run.workspace_id)
    events_payload = [dump_model(event) for event in events]
    trace_payload = [dump_model(span) for span in trace]
    return AgentRunExportBundle(
        exported_at=_utc_now(),
        run=run,
        events=events_payload,
        trace=trace_payload,
        todos=todos,
        approvals=approvals,
        artifacts=artifacts,
        workspace_snapshot=workspace_snapshot,
        summary=AgentRunExportSummary(
            run_id=run.id,
            workspace_id=run.workspace_id,
            status=str(run.status),
            event_count=len(events_payload),
            trace_span_count=len(trace_payload),
            todo_count=len(todos),
            approval_count=len(approvals),
            artifact_count=len(artifacts),
            workspace_file_count=workspace_snapshot.file_count,
        ),
    )


async def _run_export_artifact_response(
    run: AgentRun,
    body: CreateRunExportArtifactRequest,
    deps: ApiDependencies,
) -> AgentRunExportArtifactResult:
    bundle = await _build_run_export_bundle(run, deps)
    path = body.path or f"/exports/runs/{run.id}.export.json"
    name = body.name or f"Run {run.id} export"
    content = bundle.model_dump_json(indent=2)
    workspace_file = await deps.runtime.store.write_workspace_file(
        workspace_id=run.workspace_id,
        path=path,
        content=content,
        media_type="application/json",
    )
    metadata = {
        **(body.metadata or {}),
        "source": "run_export",
        "run_export": {
            "schema_version": bundle.schema_version,
            "run_id": run.id,
            "workspace_id": run.workspace_id,
            "path": workspace_file.path,
            "workspace_version": workspace_file.version,
            "file_version": workspace_file.file_version,
            "content_hash": workspace_file.content_hash,
            "event_count": bundle.summary.event_count,
            "trace_span_count": bundle.summary.trace_span_count,
            "artifact_count": bundle.summary.artifact_count,
        },
    }
    artifact = await deps.runtime.store.create_artifact(
        org_id=run.org_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        type="json",
        name=name,
        media_type="application/json",
        uri=workspace_file.path,
        content={"path": workspace_file.path},
        metadata=metadata,
        retention=body.retention,
    )
    return AgentRunExportArtifactResult(
        artifact=artifact,
        workspace_file=workspace_file,
        export_summary=bundle.summary,
        schema_version=bundle.schema_version,
        path=workspace_file.path,
    )


async def _run_tree_response(run_id: str, deps: ApiDependencies) -> RunTreeSnapshot:
    root_run = await deps.runtime.store.get_run(run_id)
    if root_run is None:
        raise RuntimeError(f"Run disappeared during tree projection: {run_id}")
    runs = await deps.runtime.store.list_runs()
    subagents = await deps.runtime.store.list_subagent_runs()
    artifacts = await deps.runtime.store.list_artifacts()
    base_snapshot = build_run_tree_snapshot(
        root_run=root_run,
        runs=runs,
        subagents=subagents,
        artifacts=artifacts,
    )
    run_ids = [node.run_id for node in base_snapshot.nodes]
    events_by_run = {}
    todos_by_run = {}
    trace_by_run = {}
    for tree_run_id in run_ids:
        events = await deps.runtime.event_store.list_by_run(tree_run_id)
        events_by_run[tree_run_id] = events
        todos_by_run[tree_run_id] = await deps.runtime.store.list_todos(tree_run_id)
        trace_by_run[tree_run_id] = project_trace_spans(events)
    return build_run_tree_snapshot(
        root_run=root_run,
        runs=runs,
        subagents=subagents,
        artifacts=artifacts,
        events_by_run=events_by_run,
        todos_by_run=todos_by_run,
        trace_by_run=trace_by_run,
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
