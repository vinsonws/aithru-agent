"""Memory routes."""

from fastapi import APIRouter, Depends, HTTPException, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    CreateMemoryEntryRequest,
    api_deps,
    filter_memory_entries_for_request,
    identity_query_value,
    identity_value,
    memory_scope_id_for_request,
    org_visible,
)
from aithru_agent.domain import AgentMemoryEntry, AgentMemoryForgetResult

router = APIRouter()


@router.post("/api/memory", status_code=201, response_model=AgentMemoryEntry)
async def create_memory_entry(
    request: Request,
    body: CreateMemoryEntryRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMemoryEntry:
    org_id = identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
    scope_id = memory_scope_id_for_request(request, body.scope, body.scope_id)
    entry = await deps.runtime.store.create_memory_entry(
        org_id=org_id,
        scope=body.scope,
        scope_id=scope_id,
        key=body.key,
        value=body.value,
        owner=body.owner,
        source=body.source,
        confidence=body.confidence,
        visibility=body.visibility,
        retention=body.retention,
    )
    return entry


@router.get("/api/memory", response_model=list[AgentMemoryEntry])
async def list_memory_entries(
    request: Request,
    org_id: str | None = None,
    scope: str | None = None,
    scope_id: str | None = None,
    query: str | None = None,
    include_expired: bool = False,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentMemoryEntry]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    resolved_scope_id = memory_scope_id_for_request(request, scope, scope_id)
    entries = await deps.runtime.store.list_memory_entries(
        org_id=resolved_org_id,
        scope=scope,
        scope_id=resolved_scope_id,
        query=query,
        include_expired=include_expired,
    )
    entries = filter_memory_entries_for_request(request, entries)
    return entries


@router.delete("/api/memory/{memory_id}", response_model=AgentMemoryForgetResult)
async def forget_memory_entry(
    request: Request,
    memory_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMemoryForgetResult:
    entry = await deps.runtime.store.get_memory_entry(memory_id)
    if (
        entry is None
        or not org_visible(request, entry.org_id)
        or not filter_memory_entries_for_request(request, [entry])
    ):
        raise HTTPException(status_code=404, detail="Memory entry not found")
    result = await deps.runtime.store.delete_memory_entry(memory_id)
    return result
