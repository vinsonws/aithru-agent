"""Agent thread message routes."""

from typing import Any

from fastapi import APIRouter, Depends, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    AppendMessageRequest,
    api_deps,
    dump_model,
)

router = APIRouter()


@router.post("/api/threads/{thread_id}/messages", status_code=201)
@router.post("/api/agent/threads/{thread_id}/messages", status_code=201)
async def append_message(
    request: Request,
    thread_id: str,
    body: AppendMessageRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    await deps.require_thread(request, thread_id)
    message = await deps.runtime.store.append_message(
        thread_id=thread_id,
        role=body.role,
        content=body.content,
    )
    return dump_model(message)


@router.get("/api/threads/{thread_id}/messages")
@router.get("/api/agent/threads/{thread_id}/messages")
async def list_messages(
    request: Request,
    thread_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    await deps.require_thread(request, thread_id)
    return [dump_model(message) for message in await deps.runtime.store.list_messages(thread_id)]

