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
    AgentApprovalPolicy,
    AgentMemoryPolicy,
    AgentSandboxPolicy,
    AgentSkill,
    AgentSkillConfiguration,
    AgentSkillEnablementResult,
    AgentSkillMarketplaceMetadata,
    AgentSkillRegistryEntry,
    AgentSkillRegistrySource,
    AgentSkillStatus,
    AgentWorkspacePolicy,
)
from aithru_agent.skills import (
    SkillRegistryError,
    SkillRegistryConflictError,
    SkillRegistryNotFoundError,
    SkillRegistryReadOnlyError,
)
from aithru_agent.skills.package_store import SkillActor
from aithru_agent.skills.packages import SkillPackage, skill_package_to_agent_skill
from aithru_agent.skills.resolver import resolve_skill_for_org

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
        for field in ("name", "version", "status", "configuration"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
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


class CreateUserSkillPackageRequest(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    body: str = Field(min_length=1)
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    allowed_subagents: list[str] = Field(default_factory=list)
    workspace_policy: AgentWorkspacePolicy | None = None
    memory_policy: AgentMemoryPolicy | None = None
    sandbox_policy: AgentSandboxPolicy | None = None
    approval_policy: AgentApprovalPolicy | None = None
    input_schema: dict[str, object] | None = None
    output_schema: dict[str, object] | None = None
    enabled: bool = True


class UpdateUserSkillPackageRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    body: str | None = Field(default=None, min_length=1)
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    allowed_subagents: list[str] | None = None
    workspace_policy: AgentWorkspacePolicy | None = None
    memory_policy: AgentMemoryPolicy | None = None
    sandbox_policy: AgentSandboxPolicy | None = None
    approval_policy: AgentApprovalPolicy | None = None
    input_schema: dict[str, object] | None = None
    output_schema: dict[str, object] | None = None
    enabled: bool | None = None


@router.post("/api/skill-registry/user", status_code=201, response_model=AgentSkillRegistryEntry)
async def create_user_skill_package(
    request: Request,
    body: CreateUserSkillPackageRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillRegistryEntry:
    actor = _skill_actor_from_request(deps, request, body_org_id=None)
    package = _build_user_skill_package(actor, body)
    try:
        saved = deps.runtime.skill_package_store.save_user_package(actor, package)
        return AgentSkillRegistryEntry.from_package(saved)
    except SkillRegistryConflictError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except SkillRegistryError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


@router.patch("/api/skill-registry/user/{skill_key}", response_model=AgentSkillRegistryEntry)
async def update_user_skill_package(
    request: Request,
    skill_key: str,
    body: UpdateUserSkillPackageRequest,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillRegistryEntry:
    actor = _skill_actor_from_request(deps, request, org_id)
    patch = _build_skill_package_patch(body)
    try:
        saved = deps.runtime.skill_package_store.update_user_package(actor, skill_key, patch)
        return AgentSkillRegistryEntry.from_package(saved)
    except SkillRegistryNotFoundError as err:
        raise HTTPException(status_code=404, detail="Skill registry entry not found") from err
    except SkillRegistryReadOnlyError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except SkillRegistryError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


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
    except SkillRegistryError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


@router.get("/api/skill-registry", response_model=list[AgentSkillRegistryEntry])
async def list_skill_registry_entries(
    request: Request,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentSkillRegistryEntry]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    actor = _skill_actor_from_request(deps, request, resolved_org_id)
    package_entries = [
        AgentSkillRegistryEntry.from_package(package)
        for package in deps.runtime.skill_package_store.list_packages(actor)
        if package.org_id == resolved_org_id
    ]
    legacy_entries = deps.runtime.skill_registry.list_entries(resolved_org_id)
    return _merge_registry_entries(package_entries, legacy_entries)


@router.get("/api/skill-registry/{entry_id_or_key}", response_model=AgentSkillRegistryEntry)
async def get_skill_registry_entry(
    request: Request,
    entry_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillRegistryEntry:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    actor = _skill_actor_from_request(deps, request, resolved_org_id)
    package = _find_package(deps, actor, entry_id_or_key, include_disabled=True)
    if package is not None:
        return AgentSkillRegistryEntry.from_package(package)
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
    except SkillRegistryError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


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
    actor = _skill_actor_from_request(deps, request)
    package_skills = [
        skill_package_to_agent_skill(package)
        for package in deps.runtime.skill_package_store.list_visible_packages(actor)
        if org_visible(request, package.org_id)
    ]
    legacy_skills = [
        skill
        for skill in deps.runtime.skill_resolver.list_skills()
        if org_visible(request, skill.org_id)
    ]
    return _merge_skills(package_skills, legacy_skills)


@router.get("/api/skills/{skill_id_or_key}", response_model=AgentSkill)
async def get_skill(
    request: Request,
    skill_id_or_key: str,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkill:
    trusted_org_id = request.headers.get("x-aithru-org-id")
    actor = _skill_actor_from_request(deps, request, trusted_org_id)
    package = _find_package(deps, actor, skill_id_or_key, include_disabled=False)
    if package is not None and org_visible(request, package.org_id):
        return skill_package_to_agent_skill(package)
    skill = (
        resolve_skill_for_org(deps.runtime.skill_resolver, trusted_org_id, skill_id_or_key)
        if trusted_org_id is not None
        else deps.runtime.skill_resolver.resolve(skill_id_or_key)
    )
    if not skill or not org_visible(request, skill.org_id):
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


def _skill_actor_from_request(
    deps: ApiDependencies,
    request: Request,
    org_id: str | None = None,
    body_org_id: str | None = None,
) -> SkillActor:
    del deps, body_org_id
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    user_id = request.headers.get("x-aithru-user-id") or "user_1"
    return SkillActor(org_id=resolved_org_id, actor_user_id=user_id)


def _build_user_skill_package(actor: object, body: CreateUserSkillPackageRequest) -> object:
    from aithru_agent.domain import AgentSkillConfiguration
    from aithru_agent.skills.package_store import SkillActor
    from aithru_agent.skills.packages import parse_skill_package, render_skill_md

    if not isinstance(actor, SkillActor):
        raise TypeError("expected SkillActor")
    skill_md = render_skill_md(name=body.name, description=body.description, body=body.body)
    policy = AgentSkillConfiguration(
        instructions="",
        when_to_use=None,
        allowed_tools=body.allowed_tools,
        denied_tools=body.denied_tools,
        allowed_subagents=body.allowed_subagents,
        workspace_policy=body.workspace_policy,
        memory_policy=body.memory_policy,
        sandbox_policy=body.sandbox_policy,
        approval_policy=body.approval_policy,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
    )
    return parse_skill_package(
        key=body.key,
        org_id=actor.org_id,
        owner_user_id=actor.actor_user_id,
        source=AgentSkillRegistrySource.USER,
        skill_md=skill_md,
        policy=policy,
        enabled=body.enabled,
    )


def _build_skill_package_patch(body: UpdateUserSkillPackageRequest) -> object:
    from aithru_agent.skills.package_store import SkillPackagePatch

    kwargs: dict[str, object] = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.description is not None:
        kwargs["description"] = body.description
    if body.body is not None:
        kwargs["body"] = body.body
    if body.allowed_tools is not None:
        kwargs["allowed_tools"] = body.allowed_tools
    if body.denied_tools is not None:
        kwargs["denied_tools"] = body.denied_tools
    if body.allowed_subagents is not None:
        kwargs["allowed_subagents"] = body.allowed_subagents
    if "workspace_policy" in body.model_fields_set:
        kwargs["workspace_policy"] = body.workspace_policy
    if "memory_policy" in body.model_fields_set:
        kwargs["memory_policy"] = body.memory_policy
    if "sandbox_policy" in body.model_fields_set:
        kwargs["sandbox_policy"] = body.sandbox_policy
    if "approval_policy" in body.model_fields_set:
        kwargs["approval_policy"] = body.approval_policy
    if "input_schema" in body.model_fields_set:
        kwargs["input_schema"] = body.input_schema
    if "output_schema" in body.model_fields_set:
        kwargs["output_schema"] = body.output_schema
    if body.enabled is not None:
        kwargs["enabled"] = body.enabled
    return SkillPackagePatch(**kwargs)


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
    actor = _skill_actor_from_request(deps, request, resolved_org_id)
    package = _find_package(deps, actor, entry_id_or_key, include_disabled=True)
    if package is not None:
        try:
            updated = deps.runtime.skill_package_store.set_user_enabled(
                actor,
                entry_id_or_key,
                enabled,
            )
            return AgentSkillEnablementResult(
                id=updated.id,
                org_id=updated.org_id,
                key=updated.key,
                enabled=updated.enabled,
                status=updated.status,
                runtime_visible=updated.status == AgentSkillStatus.PUBLISHED and updated.enabled,
                entry=AgentSkillRegistryEntry.from_package(updated),
            )
        except SkillRegistryReadOnlyError as err:
            raise HTTPException(status_code=409, detail=str(err)) from err
        except SkillRegistryNotFoundError as err:
            raise HTTPException(status_code=404, detail="Skill registry entry not found") from err
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


def _find_package(
    deps: ApiDependencies,
    actor: SkillActor,
    key_or_id: str,
    *,
    include_disabled: bool,
) -> SkillPackage | None:
    packages = (
        deps.runtime.skill_package_store.list_packages(actor)
        if include_disabled
        else deps.runtime.skill_package_store.list_visible_packages(actor)
    )
    for package in packages:
        if key_or_id in {package.key, package.id}:
            return package
    return None


def _merge_registry_entries(
    primary: list[AgentSkillRegistryEntry],
    secondary: list[AgentSkillRegistryEntry],
) -> list[AgentSkillRegistryEntry]:
    entries: list[AgentSkillRegistryEntry] = []
    seen: set[tuple[str, str]] = set()
    for entry in [*primary, *secondary]:
        key = (entry.org_id, entry.key)
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
    return sorted(entries, key=lambda entry: (entry.key, entry.id))


def _merge_skills(primary: list[AgentSkill], secondary: list[AgentSkill]) -> list[AgentSkill]:
    skills: list[AgentSkill] = []
    seen: set[tuple[str, str]] = set()
    for skill in [*primary, *secondary]:
        key = (skill.org_id, skill.key)
        if key in seen:
            continue
        seen.add(key)
        skills.append(skill)
    return sorted(skills, key=lambda skill: (skill.key, skill.id))
