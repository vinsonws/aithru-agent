"""Agent thread message routes."""

from fastapi import APIRouter, Depends, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    AppendMessageRequest,
    api_deps,
)
from aithru_agent.domain import AgentMessage

router = APIRouter()


@router.post(
    "/api/threads/{thread_id}/messages",
    status_code=201,
    response_model=AgentMessage,
)
async def append_message(
    request: Request,
    thread_id: str,
    body: AppendMessageRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMessage:
    await deps.require_thread(request, thread_id)
    message = await deps.runtime.store.append_message(
        thread_id=thread_id,
        role=body.role,
        content=body.content,
    )
    return message


@router.get("/api/threads/{thread_id}/messages", response_model=list[AgentMessage])
async def list_messages(
    request: Request,
    thread_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentMessage]:
    await deps.require_thread(request, thread_id)
    return await deps.runtime.store.list_messages(thread_id)
