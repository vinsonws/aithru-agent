"""Workspace file routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aithru_agent.api.dependencies import (
    ApiDependencies,
    WriteWorkspaceFileRequest,
    api_deps,
    dump_model,
)
from aithru_agent.domain.errors import AgentError

router = APIRouter()


@router.get("/api/agent/workspaces/{workspace_id}/files")
@router.get("/api/workspaces/{workspace_id}/files")
async def list_workspace_files(
    request: Request,
    workspace_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    await deps.require_workspace(request, workspace_id)
    return [
        dump_model(file)
        for file in await deps.runtime.store.list_workspace_files(workspace_id)
    ]


@router.get("/api/agent/workspaces/{workspace_id}/files/{path:path}")
@router.get("/api/workspaces/{workspace_id}/files/{path:path}")
async def read_workspace_file(
    request: Request,
    workspace_id: str,
    path: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    await deps.require_workspace(request, workspace_id)
    try:
        content = await deps.runtime.store.read_workspace_file(workspace_id, path)
    except AgentError as err:
        raise HTTPException(status_code=404, detail=err.message) from err
    return {"path": "/" + path.lstrip("/"), **dump_model(content)}


@router.put("/api/agent/workspaces/{workspace_id}/files/{path:path}")
@router.put("/api/workspaces/{workspace_id}/files/{path:path}")
async def write_workspace_file(
    request: Request,
    workspace_id: str,
    path: str,
    body: WriteWorkspaceFileRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    await deps.require_workspace(request, workspace_id)
    file = await deps.runtime.store.write_workspace_file(
        workspace_id=workspace_id,
        path=path,
        content=body.content,
        media_type=body.media_type,
    )
    return dump_model(file)


@router.delete("/api/agent/workspaces/{workspace_id}/files/{path:path}")
@router.delete("/api/workspaces/{workspace_id}/files/{path:path}")
async def delete_workspace_file(
    request: Request,
    workspace_id: str,
    path: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, str]:
    await deps.require_workspace(request, workspace_id)
    try:
        return await deps.runtime.store.delete_workspace_file(workspace_id, path)
    except AgentError as err:
        raise HTTPException(status_code=404, detail=err.message) from err

