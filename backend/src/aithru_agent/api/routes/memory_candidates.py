"""Memory candidate review routes."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    api_deps,
    identity_query_value,
    memory_scope_id_for_request,
    org_visible,
    run_visible,
)
from aithru_agent.domain import (
    AgentMemoryCandidate,
    AgentMemoryCandidateApprovalResult,
)
from aithru_agent.domain.errors import AgentError

router = APIRouter()


@router.get("/api/memory-candidates", response_model=list[AgentMemoryCandidate])
async def list_memory_candidates(
    request: Request,
    org_id: str | None = None,
    status: str | None = None,
    run_id: str | None = None,
    scope: str | None = None,
    scope_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentMemoryCandidate]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    resolved_scope_id = memory_scope_id_for_request(request, scope, scope_id)
    candidates = await deps.runtime.store.list_memory_candidates(
        org_id=resolved_org_id,
        status=status,
        run_id=run_id,
        scope=scope,
        scope_id=resolved_scope_id,
    )
    return await _visible_candidates(request, deps, candidates)


@router.post(
    "/api/memory-candidates/{candidate_id}/approve",
    response_model=AgentMemoryCandidateApprovalResult,
)
async def approve_memory_candidate(
    request: Request,
    candidate_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMemoryCandidateApprovalResult:
    candidate = await _require_candidate(request, deps, candidate_id)
    if candidate.status != "pending":
        raise HTTPException(status_code=409, detail="Memory candidate is already resolved")
    run = await deps.runtime.store.get_run(candidate.run_id)
    memory_entry = await deps.runtime.store.create_memory_entry(
        org_id=candidate.org_id,
        scope=candidate.scope,
        scope_id=candidate.scope_id,
        key=candidate.key,
        value=candidate.value,
        owner=run.actor_user_id if run else None,
        source="memory_candidate",
        confidence=candidate.confidence,
        retention=candidate.retention,
    )
    try:
        resolved = await deps.runtime.store.update_memory_candidate(
            candidate.id,
            org_id=candidate.org_id,
            status="approved",
            resolved_at=utc_now(),
        )
    except AgentError as err:
        raise HTTPException(status_code=404, detail="Memory candidate not found") from err
    return AgentMemoryCandidateApprovalResult(candidate=resolved, memory_entry=memory_entry)


@router.post(
    "/api/memory-candidates/{candidate_id}/reject",
    response_model=AgentMemoryCandidate,
)
async def reject_memory_candidate(
    request: Request,
    candidate_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMemoryCandidate:
    candidate = await _require_candidate(request, deps, candidate_id)
    if candidate.status != "pending":
        raise HTTPException(status_code=409, detail="Memory candidate is already resolved")
    try:
        return await deps.runtime.store.update_memory_candidate(
            candidate.id,
            org_id=candidate.org_id,
            status="rejected",
            resolved_at=utc_now(),
        )
    except AgentError as err:
        raise HTTPException(status_code=404, detail="Memory candidate not found") from err


async def _require_candidate(
    request: Request,
    deps: ApiDependencies,
    candidate_id: str,
) -> AgentMemoryCandidate:
    candidate = await deps.runtime.store.get_memory_candidate(candidate_id)
    if candidate is None or not org_visible(request, candidate.org_id):
        raise HTTPException(status_code=404, detail="Memory candidate not found")
    visible = await _visible_candidates(request, deps, [candidate])
    if not visible:
        raise HTTPException(status_code=404, detail="Memory candidate not found")
    return candidate


async def _visible_candidates(
    request: Request,
    deps: ApiDependencies,
    candidates: list[AgentMemoryCandidate],
) -> list[AgentMemoryCandidate]:
    visible: list[AgentMemoryCandidate] = []
    trusted_user_id = request.headers.get("x-aithru-user-id")
    for candidate in candidates:
        if not org_visible(request, candidate.org_id):
            continue
        if (
            trusted_user_id is not None
            and candidate.scope == "user"
            and candidate.scope_id != trusted_user_id
        ):
            continue
        run = await deps.runtime.store.get_run(candidate.run_id)
        if run is not None and not run_visible(request, run):
            continue
        visible.append(candidate)
    return visible


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
