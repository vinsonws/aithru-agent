"""Agent thread routes."""

from typing import Any

from fastapi import APIRouter, Depends, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    CreateThreadRequest,
    api_deps,
    dump_model,
    identity_value,
    thread_visible,
)

router = APIRouter()


@router.post("/api/threads", status_code=201)
@router.post("/api/agent/threads", status_code=201)
async def create_thread(
    request: Request,
    body: CreateThreadRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    org_id = identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
    owner_user_id = identity_value(
        request,
        body,
        "owner_user_id",
        body.owner_user_id,
        "x-aithru-user-id",
    )
    thread = await deps.runtime.store.create_thread(
        org_id=org_id,
        owner_user_id=owner_user_id,
        title=body.title,
    )
    return dump_model(thread)


@router.get("/api/threads")
@router.get("/api/agent/threads")
async def list_threads(
    request: Request,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    return [
        dump_model(thread)
        for thread in await deps.runtime.store.list_threads()
        if thread_visible(request, thread)
    ]


@router.get("/api/threads/{thread_id}")
@router.get("/api/agent/threads/{thread_id}")
async def get_thread(
    request: Request,
    thread_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    thread = await deps.require_thread(request, thread_id)
    return dump_model(thread)

