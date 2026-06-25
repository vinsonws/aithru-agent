"""Long-term memory provider routes."""

from fastapi import APIRouter, Depends
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
    deps: ApiDependencies = Depends(api_deps),
) -> LongTermMemoryDeleteResult:
    provider = deps.runtime.long_term_memory_provider
    return await provider.delete_memory(memory_id=memory_id)
