"""Health routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
@router.get("/api/agent/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "aithru-agent-backend"}

