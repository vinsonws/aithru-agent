"""Skill routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aithru_agent.api.dependencies import ApiDependencies, api_deps, dump_model, org_visible

router = APIRouter()


@router.get("/api/agent/skills")
@router.get("/api/skills")
async def list_skills(
    request: Request,
    deps: ApiDependencies = Depends(api_deps),
) -> list[dict[str, Any]]:
    return [
        dump_model(skill)
        for skill in deps.runtime.skill_resolver.list_skills()
        if org_visible(request, skill.org_id)
    ]


@router.get("/api/agent/skills/{skill_id_or_key}")
@router.get("/api/skills/{skill_id_or_key}")
async def get_skill(
    request: Request,
    skill_id_or_key: str,
    deps: ApiDependencies = Depends(api_deps),
) -> dict[str, Any]:
    skill = deps.runtime.skill_resolver.resolve(skill_id_or_key)
    if not skill or not org_visible(request, skill.org_id):
        raise HTTPException(status_code=404, detail="Skill not found")
    return dump_model(skill)

