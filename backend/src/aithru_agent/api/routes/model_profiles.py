"""Model profile routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from aithru_agent.api.dependencies import (
    ApiDependencies,
    api_deps,
    identity_query_value,
    identity_value,
)
from aithru_agent.domain import (
    AgentModelCapabilities,
    AgentModelProfileCostPolicy,
    AgentModelProfileDefinition,
    AgentModelProfileEnablementResult,
    AgentModelProfileEntry,
    AgentModelProfileSelectionPolicy,
    AgentModelProviderKind,
)
from aithru_agent.model_profiles import (
    ModelProfileConflictError,
    ModelProfileError,
    ModelProfileNotFoundError,
)

router = APIRouter()


class CreateModelProfileRequest(BaseModel):
    org_id: str = "org_1"
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    provider: AgentModelProviderKind
    model: str = Field(min_length=1)
    enabled: bool = True
    capabilities: AgentModelCapabilities = Field(default_factory=AgentModelCapabilities)
    cost_policy: AgentModelProfileCostPolicy = Field(
        default_factory=AgentModelProfileCostPolicy
    )
    selection_policy: AgentModelProfileSelectionPolicy = Field(
        default_factory=AgentModelProfileSelectionPolicy
    )
    metadata: dict | None = None

    def to_profile(self, *, org_id: str) -> AgentModelProfileDefinition:
        return AgentModelProfileDefinition(
            org_id=org_id,
            key=self.key,
            name=self.name,
            provider=self.provider,
            model=self.model,
            enabled=self.enabled,
            capabilities=self.capabilities,
            cost_policy=self.cost_policy,
            selection_policy=self.selection_policy,
            metadata=self.metadata,
        )


class UpdateModelProfileRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    capabilities: AgentModelCapabilities | None = None
    cost_policy: AgentModelProfileCostPolicy | None = None
    selection_policy: AgentModelProfileSelectionPolicy | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateModelProfileRequest":
        fields = {
            "name",
            "model",
            "enabled",
            "capabilities",
            "cost_policy",
            "selection_policy",
            "metadata",
        }
        if not self.model_fields_set.intersection(fields):
            raise ValueError("at least one model profile field must be supplied")
        for field in ("name", "model", "capabilities", "cost_policy", "selection_policy"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    def registry_updates(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in (
                "name",
                "model",
                "enabled",
                "capabilities",
                "cost_policy",
                "selection_policy",
                "metadata",
            )
            if field in self.model_fields_set
        }


@router.post("/api/model-profiles", status_code=201, response_model=AgentModelProfileEntry)
async def create_model_profile(
    request: Request,
    body: CreateModelProfileRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentModelProfileEntry:
    org_id = identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
    try:
        return deps.runtime.model_profile_registry.create_profile(
            body.to_profile(org_id=org_id)
        )
    except ModelProfileConflictError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except ModelProfileError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


@router.get("/api/model-profiles", response_model=list[AgentModelProfileEntry])
async def list_model_profiles(
    request: Request,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentModelProfileEntry]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    return deps.runtime.model_profile_registry.list_profiles(resolved_org_id)


@router.get("/api/model-profiles/{profile_id_or_key}", response_model=AgentModelProfileEntry)
async def get_model_profile(
    request: Request,
    profile_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentModelProfileEntry:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    profile = deps.runtime.model_profile_registry.get_profile(
        resolved_org_id,
        profile_id_or_key,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Model profile not found")
    return profile


@router.patch("/api/model-profiles/{profile_id_or_key}", response_model=AgentModelProfileEntry)
async def update_model_profile(
    request: Request,
    profile_id_or_key: str,
    body: UpdateModelProfileRequest,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentModelProfileEntry:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    try:
        return deps.runtime.model_profile_registry.update_profile(
            resolved_org_id,
            profile_id_or_key,
            body.registry_updates(),
        )
    except ModelProfileNotFoundError as err:
        raise HTTPException(status_code=404, detail="Model profile not found") from err
    except ModelProfileError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


@router.post(
    "/api/model-profiles/{profile_id_or_key}/enable",
    response_model=AgentModelProfileEnablementResult,
)
async def enable_model_profile(
    request: Request,
    profile_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentModelProfileEnablementResult:
    return _set_model_profile_enabled(
        request,
        profile_id_or_key,
        org_id=org_id,
        enabled=True,
        deps=deps,
    )


@router.post(
    "/api/model-profiles/{profile_id_or_key}/disable",
    response_model=AgentModelProfileEnablementResult,
)
async def disable_model_profile(
    request: Request,
    profile_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentModelProfileEnablementResult:
    return _set_model_profile_enabled(
        request,
        profile_id_or_key,
        org_id=org_id,
        enabled=False,
        deps=deps,
    )


def _set_model_profile_enabled(
    request: Request,
    profile_id_or_key: str,
    *,
    org_id: str | None,
    enabled: bool,
    deps: ApiDependencies,
) -> AgentModelProfileEnablementResult:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    try:
        return deps.runtime.model_profile_registry.set_enabled(
            resolved_org_id,
            profile_id_or_key,
            enabled,
        )
    except ModelProfileNotFoundError as err:
        raise HTTPException(status_code=404, detail="Model profile not found") from err
