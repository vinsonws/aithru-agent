"""Subagent spec routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    CreateSubagentSpecRequest,
    api_deps,
    dump_model,
    identity_query_value,
    identity_value,
)

router = APIRouter()


@router.post("/api/agent/subagents", status_code=201)
@router.post("/api/subagents", status_code=201)
async def create_subagent_spec(
    request: Request,
    body: CreateSubagentSpecRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    org_id = identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
    spec = await deps.runtime.store.create_subagent_spec(
        org_id=org_id,
        key=body.key,
        name=body.name,
        instructions=body.instructions,
        allowed_tools=body.allowed_tools,
    )
    return dump_model(spec)


@router.get("/api/agent/subagents")
@router.get("/api/subagents")
async def list_subagent_specs(
    request: Request,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    specs = await deps.runtime.store.list_subagent_specs(resolved_org_id)
    return [dump_model(spec) for spec in specs]


@router.get("/api/agent/subagents/{key}")
@router.get("/api/subagents/{key}")
async def get_subagent_spec(
    request: Request,
    key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    spec = await deps.runtime.store.get_subagent_spec(resolved_org_id, key)
    if not spec:
        raise HTTPException(status_code=404, detail="Subagent spec not found")
    return dump_model(spec)

