"""Memory routes."""

from typing import Any

from fastapi import APIRouter, Depends, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    CreateMemoryEntryRequest,
    api_deps,
    dump_model,
    filter_memory_entries_for_request,
    identity_query_value,
    identity_value,
    memory_scope_id_for_request,
)

router = APIRouter()


@router.post("/api/agent/memory", status_code=201)
@router.post("/api/memory", status_code=201)
async def create_memory_entry(
    request: Request,
    body: CreateMemoryEntryRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
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
    return dump_model(entry)


@router.get("/api/agent/memory")
@router.get("/api/memory")
async def list_memory_entries(
    request: Request,
    org_id: str | None = None,
    scope: str | None = None,
    scope_id: str | None = None,
    query: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    resolved_scope_id = memory_scope_id_for_request(request, scope, scope_id)
    entries = await deps.runtime.store.list_memory_entries(
        org_id=resolved_org_id,
        scope=scope,
        scope_id=resolved_scope_id,
        query=query,
    )
    entries = filter_memory_entries_for_request(request, entries)
    return [dump_model(entry) for entry in entries]

