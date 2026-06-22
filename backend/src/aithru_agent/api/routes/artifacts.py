"""Artifact routes."""

from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError

from aithru_agent.api.dependencies import ApiDependencies, api_deps
from aithru_agent.domain import (
    AgentArtifact,
    AgentArtifactDownloadInfo,
    AgentArtifactListFilters,
    AgentArtifactListOrderBy,
    AgentArtifactListOrderDirection,
    AgentArtifactListPage,
    AgentArtifactRetentionMode,
    AgentArtifactType,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.domain.errors import AgentError

router = APIRouter()

ACTIVE_CONTENT_TYPES = {
    "application/xhtml+xml",
    "image/svg+xml",
    "text/html",
}


class ArtifactContentPointer(AithruBaseModel):
    path: str = Field(min_length=1)


class ArtifactListQuery(BaseModel):
    run_id: str | None = None
    workspace_id: str | None = None
    type: AgentArtifactType | None = None
    retention_mode: AgentArtifactRetentionMode | None = None
    finalized: bool | None = None
    include_meta: bool = False
    order_by: AgentArtifactListOrderBy | None = None
    order_direction: AgentArtifactListOrderDirection = "asc"
    limit: int | None = Field(default=None, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


@router.get("/api/artifacts", response_model=AgentArtifactListPage | list[AgentArtifact])
async def list_artifacts(
    request: Request,
    query: ArtifactListQuery = Depends(),
    deps: ApiDependencies = Depends(api_deps),
) -> AgentArtifactListPage | list[AgentArtifact]:
    filters = AgentArtifactListFilters(
        run_id=query.run_id,
        workspace_id=query.workspace_id,
        type=query.type,
        retention_mode=query.retention_mode,
        finalized=query.finalized,
    )
    if filters.run_id is not None:
        await deps.require_run(request, filters.run_id)
    if filters.workspace_id is not None:
        await deps.require_workspace(request, filters.workspace_id)
    artifacts = []
    for artifact in await deps.runtime.store.list_artifacts(
        run_id=filters.run_id,
        workspace_id=filters.workspace_id,
        type=filters.type,
        retention_mode=filters.retention_mode,
        finalized=filters.finalized,
    ):
        if await deps.artifact_visible(request, artifact):
            artifacts.append(artifact)
    page = _build_artifact_list_page(artifacts, query, filters)
    if query.include_meta:
        return page
    return page.items


@router.get("/api/artifacts/{artifact_id}", response_model=AgentArtifact)
async def get_artifact(
    request: Request,
    artifact_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentArtifact:
    artifact = await deps.require_artifact(request, artifact_id)
    return artifact


@router.get("/api/artifacts/{artifact_id}/content")
async def get_artifact_content(
    request: Request,
    artifact_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> Response:
    artifact = await deps.require_artifact(request, artifact_id)
    content, media_type = await _artifact_content(artifact, deps)
    headers = _content_headers(artifact, media_type)
    return Response(content=content, media_type=media_type, headers=headers)


@router.get(
    "/api/artifacts/{artifact_id}/download-info",
    response_model=AgentArtifactDownloadInfo,
)
async def get_artifact_download_info(
    request: Request,
    artifact_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentArtifactDownloadInfo:
    artifact = await deps.require_artifact(request, artifact_id)
    content, media_type = await _artifact_content(artifact, deps)
    return _download_info(artifact, content, media_type, disposition="attachment")


@router.get("/api/artifacts/{artifact_id}/download")
async def download_artifact(
    request: Request,
    artifact_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> Response:
    artifact = await deps.require_artifact(request, artifact_id)
    content, media_type = await _artifact_content(artifact, deps)
    info = _download_info(artifact, content, media_type, disposition="attachment")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": _content_disposition(info)},
    )


async def _artifact_content(
    artifact: AgentArtifact,
    deps: ApiDependencies,
) -> tuple[str | bytes, str]:
    pointer = _content_pointer(artifact)
    if pointer is not None:
        try:
            workspace_content = await deps.runtime.store.read_workspace_file(
                artifact.workspace_id,
                pointer.path,
            )
        except AgentError as err:
            raise HTTPException(status_code=404, detail="Artifact content not found") from err
        return (
            workspace_content.content,
            artifact.media_type or workspace_content.media_type or "application/octet-stream",
        )
    if isinstance(artifact.content, str | bytes):
        return artifact.content, artifact.media_type or "text/plain"
    raise HTTPException(status_code=404, detail="Artifact content not found")


def _content_pointer(artifact: AgentArtifact) -> ArtifactContentPointer | None:
    if isinstance(artifact.content, dict):
        try:
            return ArtifactContentPointer.model_validate(artifact.content)
        except ValidationError:
            return None
    if artifact.uri and artifact.uri.startswith("/"):
        return ArtifactContentPointer(path=artifact.uri)
    return None


def _content_headers(artifact: AgentArtifact, media_type: str) -> dict[str, str]:
    normalized = media_type.split(";", 1)[0].lower()
    if normalized not in ACTIVE_CONTENT_TYPES:
        return {}
    return {
        "Content-Disposition": _content_disposition(
            AgentArtifactDownloadInfo(
                artifact_id=artifact.id,
                filename=_download_filename(artifact),
                media_type=media_type,
                content_length=0,
                disposition="attachment",
                source_path=_content_pointer(artifact).path if _content_pointer(artifact) else None,
            )
        )
    }


def _download_info(
    artifact: AgentArtifact,
    content: str | bytes,
    media_type: str,
    *,
    disposition: str,
) -> AgentArtifactDownloadInfo:
    pointer = _content_pointer(artifact)
    return AgentArtifactDownloadInfo(
        artifact_id=artifact.id,
        filename=_download_filename(artifact),
        media_type=media_type,
        content_length=_content_length(content),
        disposition=disposition,
        source_path=pointer.path if pointer else None,
    )


def _content_length(content: str | bytes) -> int:
    if isinstance(content, bytes):
        return len(content)
    return len(content.encode("utf-8"))


def _content_disposition(info: AgentArtifactDownloadInfo) -> str:
    return f'{info.disposition}; filename="{info.filename}"'


def _download_filename(artifact: AgentArtifact) -> str:
    stem = "_".join(part for part in artifact.name.strip().split() if part)
    if not stem:
        stem = artifact.id
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    suffix = PurePosixPath(artifact.uri or "").suffix
    if not suffix and artifact.media_type == "text/html":
        suffix = ".html"
    return f"{safe_stem}{suffix}"


def _build_artifact_list_page(
    artifacts: list[AgentArtifact],
    query: ArtifactListQuery,
    filters: AgentArtifactListFilters,
) -> AgentArtifactListPage:
    sorted_artifacts = _sort_artifacts(artifacts, query)
    items = _paginate_artifacts(sorted_artifacts, query)
    return AgentArtifactListPage(
        items=items,
        total=len(artifacts),
        count=len(items),
        limit=query.limit,
        offset=query.offset,
        order_by=query.order_by,
        order_direction=query.order_direction,
        filters=filters,
    )


def _sort_artifacts(
    artifacts: list[AgentArtifact],
    query: ArtifactListQuery,
) -> list[AgentArtifact]:
    if query.order_by is None:
        return artifacts
    present: list[tuple[str, AgentArtifact]] = []
    missing: list[AgentArtifact] = []
    for artifact in artifacts:
        value = _artifact_order_value(artifact, query.order_by)
        if value is None:
            missing.append(artifact)
        else:
            present.append((value, artifact))
    present.sort(key=lambda item: item[0], reverse=query.order_direction == "desc")
    return [artifact for _, artifact in present] + missing


def _artifact_order_value(
    artifact: AgentArtifact,
    order_by: AgentArtifactListOrderBy,
) -> str | None:
    value = getattr(artifact, order_by)
    if isinstance(value, str):
        return value
    return None


def _paginate_artifacts(
    artifacts: list[AgentArtifact],
    query: ArtifactListQuery,
) -> list[AgentArtifact]:
    offset_artifacts = artifacts[query.offset :]
    if query.limit is None:
        return offset_artifacts
    return offset_artifacts[: query.limit]
