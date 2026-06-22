"""Skill routes."""

from fastapi import APIRouter, Depends, HTTPException, Request

from aithru_agent.api.dependencies import ApiDependencies, api_deps, org_visible
from aithru_agent.domain import AgentSkill

router = APIRouter()


@router.get("/api/skills", response_model=list[AgentSkill])
async def list_skills(
    request: Request,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentSkill]:
    return [
        skill
        for skill in deps.runtime.skill_resolver.list_skills()
        if org_visible(request, skill.org_id)
    ]


@router.get("/api/skills/{skill_id_or_key}", response_model=AgentSkill)
async def get_skill(
    request: Request,
    skill_id_or_key: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkill:
    skill = deps.runtime.skill_resolver.resolve(skill_id_or_key)
    if not skill or not org_visible(request, skill.org_id):
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill
