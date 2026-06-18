"""Approval routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    ResolveApprovalRequest,
    api_deps,
    dump_model,
)
from aithru_agent.domain.errors import AgentError

router = APIRouter()


@router.get("/api/agent/approvals")
@router.get("/api/approvals")
async def list_approvals(
    request: Request,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    approvals = []
    for approval in await deps.runtime.store.list_approvals():
        if await deps.approval_visible(request, approval):
            approvals.append(dump_model(approval))
    return approvals


@router.get("/api/agent/approvals/{approval_id}")
@router.get("/api/approvals/{approval_id}")
async def get_approval(
    request: Request,
    approval_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    approval = await deps.require_approval(request, approval_id)
    return dump_model(approval)


@router.post("/api/agent/runs/{run_id}/resume")
@router.post("/api/runs/{run_id}/resume")
async def resume_run(
    request: Request,
    run_id: str,
    body: ResolveApprovalRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
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
    return dump_model(resumed)


@router.post("/api/agent/approvals/{approval_id}/resolve")
@router.post("/api/approvals/{approval_id}/resolve")
async def resolve_approval(
    request: Request,
    approval_id: str,
    body: ResolveApprovalRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
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
    return dump_model(resolved)

