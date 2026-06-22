"""Subagent spec routes."""

from fastapi import APIRouter, Depends, HTTPException, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    CreateSubagentSpecRequest,
    api_deps,
    identity_query_value,
    identity_value,
)
from aithru_agent.domain import AgentSubagentSpec

router = APIRouter()


@router.post("/api/subagents", status_code=201, response_model=AgentSubagentSpec)
async def create_subagent_spec(
    request: Request,
    body: CreateSubagentSpecRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSubagentSpec:
    org_id = identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
    spec = await deps.runtime.store.create_subagent_spec(
        org_id=org_id,
        key=body.key,
        name=body.name,
        instructions=body.instructions,
        allowed_tools=body.allowed_tools,
    )
    return spec


@router.get("/api/subagents", response_model=list[AgentSubagentSpec])
async def list_subagent_specs(
    request: Request,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentSubagentSpec]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    return await deps.runtime.store.list_subagent_specs(resolved_org_id)


@router.get("/api/subagents/{key}", response_model=AgentSubagentSpec)
async def get_subagent_spec(
    request: Request,
    key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSubagentSpec:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    spec = await deps.runtime.store.get_subagent_spec(resolved_org_id, key)
    if not spec:
        raise HTTPException(status_code=404, detail="Subagent spec not found")
    return spec
