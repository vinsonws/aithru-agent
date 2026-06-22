"""Health routes."""

from typing import Literal

from fastapi import APIRouter

from aithru_agent.domain.base import AithruBaseModel

router = APIRouter()


class AgentHealthResponse(AithruBaseModel):
    ok: Literal[True] = True
    service: Literal["aithru-agent-backend"] = "aithru-agent-backend"


@router.get("/api/health", response_model=AgentHealthResponse)
async def health() -> AgentHealthResponse:
    return AgentHealthResponse()
