"""Workspace file routes."""

from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from aithru_agent.api.dependencies import (
    ApiDependencies,
    PatchWorkspaceFileRequest,
    PromoteWorkspaceFileRequest,
    RestoreWorkspaceSnapshotRequest,
    UploadWorkspaceFileRequest,
    WriteWorkspaceFileRequest,
    api_deps,
)
from aithru_agent.domain import (
    AgentArtifactPromotionResult,
    AgentWorkspaceDiff,
    AgentWorkspaceFile,
    AgentWorkspaceFileDeleteResult,
    AgentWorkspaceFileVersion,
    AgentWorkspaceFileReadResult,
    AgentWorkspaceImageViewResult,
    AgentWorkspacePatchResult,
    AgentWorkspaceRestoreResult,
    AgentWorkspaceSnapshot,
    AgentWorkspaceTextPatchRequest,
    AgentWorkspaceUploadResult,
    apply_workspace_text_patch,
    workspace_image_content_base64,
)
from aithru_agent.domain.errors import AgentError

router = APIRouter()


@router.get(
    "/api/workspaces/{workspace_id}/snapshot",
    response_model=AgentWorkspaceSnapshot,
)
async def get_workspace_snapshot(
    request: Request,
    workspace_id: str,
    version: int | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentWorkspaceSnapshot:
    await deps.require_workspace(request, workspace_id)
    return await deps.runtime.store.get_workspace_snapshot(workspace_id, version=version)


@router.get("/api/workspaces/{workspace_id}/diff", response_model=AgentWorkspaceDiff)
async def get_workspace_diff(
    request: Request,
    workspace_id: str,
    base_version: int | None = None,
    target_version: int | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentWorkspaceDiff:
    await deps.require_workspace(request, workspace_id)
    return await deps.runtime.store.diff_workspace_snapshots(
        workspace_id=workspace_id,
        base_version=base_version,
        target_version=target_version,
    )


@router.post(
    "/api/workspaces/{workspace_id}/restore",
    response_model=AgentWorkspaceRestoreResult,
)
async def restore_workspace_snapshot(
    request: Request,
    workspace_id: str,
    body: RestoreWorkspaceSnapshotRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentWorkspaceRestoreResult:
    await deps.require_workspace(request, workspace_id)
    return await deps.runtime.store.restore_workspace_snapshot(
        workspace_id,
        version=body.version,
    )


@router.get(
    "/api/workspaces/{workspace_id}/files",
    response_model=list[AgentWorkspaceFile],
)
async def list_workspace_files(
    request: Request,
    workspace_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentWorkspaceFile]:
    await deps.require_workspace(request, workspace_id)
    return await deps.runtime.store.list_workspace_files(workspace_id)


@router.get(
    "/api/workspaces/{workspace_id}/files/{path:path}/versions",
    response_model=list[AgentWorkspaceFileVersion],
)
async def list_workspace_file_versions(
    request: Request,
    workspace_id: str,
    path: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentWorkspaceFileVersion]:
    await deps.require_workspace(request, workspace_id)
    return await deps.runtime.store.list_workspace_file_versions(
        workspace_id=workspace_id,
        path=path,
    )


@router.post(
    "/api/workspaces/{workspace_id}/uploads",
    status_code=201,
    response_model=AgentWorkspaceUploadResult,
)
async def upload_workspace_file(
    request: Request,
    workspace_id: str,
    body: UploadWorkspaceFileRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentWorkspaceUploadResult:
    await deps.require_workspace(request, workspace_id)
    existing = await _workspace_file_metadata_or_none(
        deps,
        workspace_id=workspace_id,
        path=body.path,
    )
    file = await deps.runtime.store.write_workspace_file(
        workspace_id=workspace_id,
        path=body.path,
        content=body.content_bytes(),
        media_type=body.media_type,
    )
    return AgentWorkspaceUploadResult(
        workspace_id=workspace_id,
        path=file.path,
        file=file,
        size=file.size,
        media_type=file.media_type,
        overwritten=existing is not None,
    )


@router.get(
    "/api/workspaces/{workspace_id}/images/{path:path}/view",
    response_model=AgentWorkspaceImageViewResult,
)
async def view_workspace_image(
    request: Request,
    workspace_id: str,
    path: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentWorkspaceImageViewResult:
    await deps.require_workspace(request, workspace_id)
    try:
        file = await _workspace_file_metadata(deps, workspace_id=workspace_id, path=path)
        content = await deps.runtime.store.read_workspace_file(workspace_id, path)
        return AgentWorkspaceImageViewResult(
            workspace_id=workspace_id,
            path=file.path,
            media_type=file.media_type or "",
            size=file.size,
            content_hash=file.content_hash,
            content_base64=workspace_image_content_base64(content.content),
        )
    except AgentError as err:
        raise HTTPException(status_code=404, detail=err.message) from err
    except ValidationError as err:
        raise _workspace_image_http_error(err) from err


@router.post(
    "/api/workspaces/{workspace_id}/files/{path:path}/promote",
    status_code=201,
    response_model=AgentArtifactPromotionResult,
)
async def promote_workspace_file_to_artifact(
    request: Request,
    workspace_id: str,
    path: str,
    body: PromoteWorkspaceFileRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentArtifactPromotionResult:
    workspace = await deps.require_workspace(request, workspace_id)
    if body.run_id is not None:
        run = await deps.require_run(request, body.run_id)
        if run.workspace_id != workspace_id:
            raise HTTPException(status_code=409, detail="Run does not belong to workspace")
    normalized_request_path = "/" + path.lstrip("/")
    name = body.name or PurePosixPath(normalized_request_path).name or normalized_request_path
    try:
        return await deps.runtime.store.promote_workspace_file_to_artifact(
            org_id=workspace.org_id,
            workspace_id=workspace_id,
            path=path,
            name=name,
            type=body.type,
            run_id=body.run_id,
            retention=body.retention,
            metadata=body.metadata,
        )
    except AgentError as err:
        if err.code == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=err.message) from err
        raise HTTPException(status_code=409, detail=err.message) from err


@router.post(
    "/api/workspaces/{workspace_id}/files/{path:path}/patch",
    response_model=AgentWorkspacePatchResult,
)
async def patch_workspace_file(
    request: Request,
    workspace_id: str,
    path: str,
    body: PatchWorkspaceFileRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentWorkspacePatchResult:
    await deps.require_workspace(request, workspace_id)
    patch_request = AgentWorkspaceTextPatchRequest(
        path="/" + path.lstrip("/"),
        edits=body.edits,
        media_type=body.media_type,
    )
    try:
        current = await deps.runtime.store.read_workspace_file(workspace_id, path)
        before_file = await _workspace_file_metadata(deps, workspace_id=workspace_id, path=path)
    except AgentError as err:
        raise HTTPException(status_code=404, detail=err.message) from err
    if not isinstance(current.content, str):
        raise HTTPException(status_code=409, detail="Workspace patch only supports text files")
    try:
        patched_content, replacement_count = apply_workspace_text_patch(
            current.content,
            patch_request,
        )
    except ValueError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    patched_file = await deps.runtime.store.write_workspace_file(
        workspace_id=workspace_id,
        path=path,
        content=patched_content,
        media_type=patch_request.media_type or current.media_type,
    )
    return AgentWorkspacePatchResult(
        workspace_id=workspace_id,
        path=patched_file.path,
        version_before=before_file.version,
        version_after=patched_file.version,
        file_version_before=before_file.file_version,
        file_version_after=patched_file.file_version,
        size_before=before_file.size,
        size_after=patched_file.size,
        replacement_count=replacement_count,
        content_hash=patched_file.content_hash,
    )


@router.get(
    "/api/workspaces/{workspace_id}/files/{path:path}",
    response_model=AgentWorkspaceFileReadResult,
)
async def read_workspace_file(
    request: Request,
    workspace_id: str,
    path: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentWorkspaceFileReadResult:
    await deps.require_workspace(request, workspace_id)
    try:
        content = await deps.runtime.store.read_workspace_file(workspace_id, path)
    except AgentError as err:
        raise HTTPException(status_code=404, detail=err.message) from err
    return AgentWorkspaceFileReadResult(
        path="/" + path.lstrip("/"),
        content=content.content,
        media_type=content.media_type,
    )


@router.put(
    "/api/workspaces/{workspace_id}/files/{path:path}",
    response_model=AgentWorkspaceFile,
)
async def write_workspace_file(
    request: Request,
    workspace_id: str,
    path: str,
    body: WriteWorkspaceFileRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentWorkspaceFile:
    await deps.require_workspace(request, workspace_id)
    return await deps.runtime.store.write_workspace_file(
        workspace_id=workspace_id,
        path=path,
        content=body.content,
        media_type=body.media_type,
    )


@router.delete(
    "/api/workspaces/{workspace_id}/files/{path:path}",
    response_model=AgentWorkspaceFileDeleteResult,
)
async def delete_workspace_file(
    request: Request,
    workspace_id: str,
    path: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentWorkspaceFileDeleteResult:
    await deps.require_workspace(request, workspace_id)
    try:
        return AgentWorkspaceFileDeleteResult.model_validate(
            await deps.runtime.store.delete_workspace_file(workspace_id, path)
        )
    except AgentError as err:
        raise HTTPException(status_code=404, detail=err.message) from err


async def _workspace_file_metadata(
    deps: ApiDependencies,
    *,
    workspace_id: str,
    path: str,
) -> AgentWorkspaceFile:
    normalized_path = "/" + path.lstrip("/")
    for file in await deps.runtime.store.list_workspace_files(workspace_id):
        if file.path == normalized_path:
            return file
    raise AgentError("NOT_FOUND", f"Workspace file not found: {normalized_path}")


async def _workspace_file_metadata_or_none(
    deps: ApiDependencies,
    *,
    workspace_id: str,
    path: str,
) -> AgentWorkspaceFile | None:
    try:
        return await _workspace_file_metadata(deps, workspace_id=workspace_id, path=path)
    except AgentError:
        return None


def _workspace_image_http_error(err: ValidationError) -> HTTPException:
    message = "; ".join(str(error.get("msg", "")) for error in err.errors()) or str(err)
    if "Unsupported image media type" in message:
        return HTTPException(status_code=415, detail=message)
    if "maximum image size" in message:
        return HTTPException(status_code=413, detail=message)
    return HTTPException(status_code=409, detail=message)
