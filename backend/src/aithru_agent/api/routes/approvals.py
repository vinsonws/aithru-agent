"""Approval routes."""

from typing import Literal, Self

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, model_validator

from aithru_agent.api.dependencies import (
    ApiDependencies,
    ResolveApprovalRequest,
    ResolveExternalApprovalRequest,
    ResolveExternalRunRequest,
    api_deps,
    dump_model,
)
from aithru_agent.domain import AgentApproval, AgentRun, AgentRunStatus
from aithru_agent.domain.errors import AgentError

router = APIRouter()


ExternalRunResolveStatus = Literal["completed", "failed", "cancelled"]


class ResolveExternalRunResponse(AgentRun):
    external_run_resolved: Literal[True] = True
    external_run_capability_run_id: str = Field(min_length=1)
    external_run_status: ExternalRunResolveStatus
    external_run_idempotent: bool = False
    external_run_requeued: bool = False

    @model_validator(mode="after")
    def _requeue_only_for_fresh_completed_callbacks(self) -> Self:
        if self.external_run_requeued and (
            self.external_run_idempotent
            or self.external_run_status != "completed"
            or self.status != AgentRunStatus.QUEUED
        ):
            raise ValueError("external run requeue requires a fresh completed callback")
        return self


@router.get("/api/approvals", response_model=list[AgentApproval])
async def list_approvals(
    request: Request,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentApproval]:
    approvals = []
    for approval in await deps.runtime.store.list_approvals():
        if await deps.approval_visible(request, approval):
            approvals.append(approval)
    return approvals


@router.get("/api/approvals/{approval_id}", response_model=AgentApproval)
async def get_approval(
    request: Request,
    approval_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentApproval:
    approval = await deps.require_approval(request, approval_id)
    return approval


@router.post("/api/runs/{run_id}/resume", response_model=AgentRun)
async def resume_run(
    request: Request,
    run_id: str,
    body: ResolveApprovalRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRun:
    run = await deps.require_run(request, run_id)
    approval_id = body.approval_id or run.current_approval_id
    if not approval_id:
        raise HTTPException(status_code=409, detail="Run is not waiting for approval")
    try:
        resumed = await deps.runtime.runner.resume_run(
            run_id,
            approval_id=approval_id,
            decision=body.decision,
            comment=body.comment,
        )
    except AgentError as err:
        raise HTTPException(status_code=409, detail=err.message) from err
    return resumed


@router.post("/api/runs/{run_id}/external-approval/resolve", response_model=AgentRun)
async def resolve_external_approval(
    request: Request,
    run_id: str,
    body: ResolveExternalApprovalRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentRun:
    run = await deps.require_run(request, run_id)
    external = run.current_external_approval
    approval_id = body.approval_id or (external.approval_id if external else None)
    if not approval_id:
        raise HTTPException(status_code=409, detail="Run is not waiting for external approval")
    try:
        resumed = await deps.runtime.runner.resume_after_external_approval(
            run_id,
            approval_id=approval_id,
            capability_run_id=body.capability_run_id,
            decision=body.decision,
            comment=body.comment,
        )
    except AgentError as err:
        raise HTTPException(status_code=409, detail=err.message) from err
    return resumed


@router.post(
    "/api/runs/{run_id}/external-run/resolve",
    response_model=ResolveExternalRunResponse,
)
async def resolve_external_run(
    request: Request,
    run_id: str,
    body: ResolveExternalRunRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> ResolveExternalRunResponse:
    run = await deps.require_run(request, run_id)
    idempotent = run.status != AgentRunStatus.WAITING_EXTERNAL_RUN
    try:
        resolved = await deps.runtime.runner.resume_after_external_run(
            run_id,
            capability_run_id=body.capability_run_id,
            status=body.status,
            output=body.output,
            error=body.error,
            comment=body.comment,
        )
    except AgentError as err:
        raise HTTPException(status_code=409, detail=err.message) from err
    requeued = (
        not idempotent
        and body.status == "completed"
        and resolved.status == AgentRunStatus.QUEUED
    )
    if requeued:
        deps.runtime.worker.queue.enqueue(resolved.id)
    return ResolveExternalRunResponse.model_validate(
        {
            **dump_model(resolved),
            "external_run_capability_run_id": body.capability_run_id,
            "external_run_status": body.status,
            "external_run_idempotent": idempotent,
            "external_run_requeued": requeued,
        }
    )


@router.post("/api/approvals/{approval_id}/resolve", response_model=AgentApproval)
async def resolve_approval(
    request: Request,
    approval_id: str,
    body: ResolveApprovalRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentApproval:
    approval = await deps.require_approval(request, approval_id)
    try:
        await deps.runtime.runner.resume_run(
            approval.run_id,
            approval_id=approval_id,
            decision=body.decision,
            comment=body.comment,
        )
    except AgentError as err:
        raise HTTPException(status_code=409, detail=err.message) from err
    resolved = await deps.runtime.store.get_approval(approval_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return resolved
