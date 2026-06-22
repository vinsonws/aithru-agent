"""Skill routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from aithru_agent.api.dependencies import (
    ApiDependencies,
    api_deps,
    identity_query_value,
    org_visible,
)
from aithru_agent.domain import (
    AgentSkill,
    AgentSkillConfiguration,
    AgentSkillEnablementResult,
    AgentSkillMarketplaceMetadata,
    AgentSkillRegistryEntry,
    AgentSkillRegistrySource,
    AgentSkillStatus,
)
from aithru_agent.skills import (
    SkillRegistryConflictError,
    SkillRegistryNotFoundError,
    SkillRegistryReadOnlyError,
)

router = APIRouter()


class RegisterSkillRegistryEntryRequest(BaseModel):
    skill: AgentSkill
    source: AgentSkillRegistrySource = AgentSkillRegistrySource.MANAGED
    marketplace: AgentSkillMarketplaceMetadata | None = None


class UpdateSkillRegistryEntryRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    version: str | None = Field(default=None, min_length=1)
    status: AgentSkillStatus | None = None
    marketplace: AgentSkillMarketplaceMetadata | None = None
    configuration: AgentSkillConfiguration | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateSkillRegistryEntryRequest":
        if not self.model_fields_set.intersection(
            {"name", "description", "version", "status", "marketplace", "configuration"}
        ):
            raise ValueError("at least one skill registry field must be supplied")
        return self

    def registry_updates(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in (
                "name",
                "description",
                "version",
                "status",
                "marketplace",
                "configuration",
            )
            if field in self.model_fields_set
        }


@router.post("/api/skill-registry", status_code=201, response_model=AgentSkillRegistryEntry)
async def register_skill_registry_entry(
    request: Request,
    body: RegisterSkillRegistryEntryRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillRegistryEntry:
    _require_skill_org(request, body.skill.org_id)
    if body.source == AgentSkillRegistrySource.BUILTIN:
        raise HTTPException(
            status_code=400,
            detail="Built-in skill entries are managed by the platform",
        )
    try:
        return deps.runtime.skill_registry.register_skill(
            body.skill,
            source=body.source,
            marketplace=body.marketplace,
        )
    except SkillRegistryConflictError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


@router.get("/api/skill-registry", response_model=list[AgentSkillRegistryEntry])
async def list_skill_registry_entries(
    request: Request,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentSkillRegistryEntry]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    return deps.runtime.skill_registry.list_entries(resolved_org_id)


@router.get("/api/skill-registry/{entry_id_or_key}", response_model=AgentSkillRegistryEntry)
async def get_skill_registry_entry(
    request: Request,
    entry_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillRegistryEntry:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    entry = deps.runtime.skill_registry.get_entry(resolved_org_id, entry_id_or_key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Skill registry entry not found")
    return entry


@router.patch("/api/skill-registry/{entry_id_or_key}", response_model=AgentSkillRegistryEntry)
async def update_skill_registry_entry(
    request: Request,
    entry_id_or_key: str,
    body: UpdateSkillRegistryEntryRequest,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillRegistryEntry:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    try:
        return deps.runtime.skill_registry.update_entry(
            resolved_org_id,
            entry_id_or_key,
            body.registry_updates(),
        )
    except SkillRegistryNotFoundError as err:
        raise HTTPException(status_code=404, detail="Skill registry entry not found") from err
    except SkillRegistryReadOnlyError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


@router.post(
    "/api/skill-registry/{entry_id_or_key}/enable",
    response_model=AgentSkillEnablementResult,
)
async def enable_skill_registry_entry(
    request: Request,
    entry_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillEnablementResult:
    return _set_skill_registry_entry_enabled(
        request,
        entry_id_or_key,
        org_id=org_id,
        enabled=True,
        deps=deps,
    )


@router.post(
    "/api/skill-registry/{entry_id_or_key}/disable",
    response_model=AgentSkillEnablementResult,
)
async def disable_skill_registry_entry(
    request: Request,
    entry_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillEnablementResult:
    return _set_skill_registry_entry_enabled(
        request,
        entry_id_or_key,
        org_id=org_id,
        enabled=False,
        deps=deps,
    )


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


def _require_skill_org(request: Request, skill_org_id: str) -> None:
    trusted_org_id = request.headers.get("x-aithru-org-id")
    if trusted_org_id is not None and skill_org_id != trusted_org_id:
        raise HTTPException(
            status_code=403,
            detail="Request identity conflicts with authenticated context",
        )


def _set_skill_registry_entry_enabled(
    request: Request,
    entry_id_or_key: str,
    *,
    org_id: str | None,
    enabled: bool,
    deps: ApiDependencies,
) -> AgentSkillEnablementResult:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    try:
        return deps.runtime.skill_registry.set_enabled(
            resolved_org_id,
            entry_id_or_key,
            enabled,
        )
    except SkillRegistryNotFoundError as err:
        raise HTTPException(status_code=404, detail="Skill registry entry not found") from err
    except SkillRegistryReadOnlyError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
