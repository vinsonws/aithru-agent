"""Long-term memory provider routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from aithru_agent.api.dependencies import ApiDependencies, api_deps
from aithru_agent.memory import LongTermMemoryDeleteResult


router = APIRouter()


class LongTermMemoryHealth(BaseModel):
    provider: str
    enabled: bool


@router.get("/api/long-term-memory/health", response_model=LongTermMemoryHealth)
async def long_term_memory_health(
    deps: ApiDependencies = Depends(api_deps),
) -> LongTermMemoryHealth:
    provider = deps.runtime.settings.long_term_memory.provider
    return LongTermMemoryHealth(
        provider=provider,
        enabled=provider == "mem0",
    )


@router.delete(
    "/api/long-term-memory/{memory_id}",
    response_model=LongTermMemoryDeleteResult,
)
async def delete_long_term_memory(
    memory_id: str,
    request: Request,
    deps: ApiDependencies = Depends(api_deps),
) -> LongTermMemoryDeleteResult:
    org_id = request.headers.get("x-aithru-org-id")
    actor_user_id = request.headers.get("x-aithru-user-id")
    if not org_id or not actor_user_id:
        raise HTTPException(
            status_code=403,
            detail="X-Aithru-Org-Id and X-Aithru-User-Id headers are required for long-term memory deletion",
        )
    if not scopes_allowed_for_long_term_memory(deps):
        raise HTTPException(
            status_code=403,
            detail="Insufficient scopes for long-term memory deletion",
        )
    provider = deps.runtime.long_term_memory_provider
    return await provider.delete_memory(memory_id=memory_id)


def scopes_allowed_for_long_term_memory(deps: ApiDependencies) -> bool:
    allowed = deps.runtime.settings.api_scopes
    if "*" in allowed:
        return True
    return "agent.memory.write" in allowed
