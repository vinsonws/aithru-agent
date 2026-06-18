"""Artifact routes."""

from typing import Any

from fastapi import APIRouter, Depends, Request

from aithru_agent.api.dependencies import ApiDependencies, api_deps, dump_model

router = APIRouter()


@router.get("/api/agent/artifacts")
@router.get("/api/artifacts")
async def list_artifacts(
    request: Request,
    run_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    if run_id is not None:
        await deps.require_run(request, run_id)
    artifacts = []
    for artifact in await deps.runtime.store.list_artifacts(run_id=run_id):
        if await deps.artifact_visible(request, artifact):
            artifacts.append(dump_model(artifact))
    return artifacts


@router.get("/api/agent/artifacts/{artifact_id}")
@router.get("/api/artifacts/{artifact_id}")
async def get_artifact(
    request: Request,
    artifact_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    artifact = await deps.require_artifact(request, artifact_id)
    return dump_model(artifact)

