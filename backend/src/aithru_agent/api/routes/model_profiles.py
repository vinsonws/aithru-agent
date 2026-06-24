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
    AgentModelProfileSecretStatus,
    AgentModelProviderKind,
)
from aithru_agent.model_profiles import (
    ModelProfileConflictError,
    ModelProfileError,
    ModelProfileNotFoundError,
)
from aithru_agent.secrets import model_profile_api_key_secret_ref

router = APIRouter()


class ModelProfileSecretInput(BaseModel):
    secret_ref: str | None = None
    write_only_value: object | None = Field(
        default=None,
        description="Write-only provider API key stored in the Agent secret store.",
        json_schema_extra={"writeOnly": True},
    )


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
    auth_secret: ModelProfileSecretInput | None = None
    metadata: dict | None = None

    def to_profile(
        self,
        *,
        org_id: str,
        auth_secret: AgentModelProfileSecretStatus | None,
    ) -> AgentModelProfileDefinition:
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
            auth_secret=auth_secret,
            metadata=self.metadata,
        )


class UpdateModelProfileRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    provider: AgentModelProviderKind | None = None
    model: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    capabilities: AgentModelCapabilities | None = None
    cost_policy: AgentModelProfileCostPolicy | None = None
    selection_policy: AgentModelProfileSelectionPolicy | None = None
    auth_secret: ModelProfileSecretInput | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateModelProfileRequest":
        fields = {
            "name",
            "provider",
            "model",
            "enabled",
            "capabilities",
            "cost_policy",
            "selection_policy",
            "auth_secret",
            "metadata",
        }
        if not self.model_fields_set.intersection(fields):
            raise ValueError("at least one model profile field must be supplied")
        for field in (
            "name",
            "provider",
            "model",
            "capabilities",
            "cost_policy",
            "selection_policy",
            "auth_secret",
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    def registry_updates(
        self,
        *,
        auth_secret: AgentModelProfileSecretStatus | None = None,
    ) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in (
                "name",
                "provider",
                "model",
                "enabled",
                "capabilities",
                "cost_policy",
                "selection_policy",
            )
            if field in self.model_fields_set
        } | (
            {"auth_secret": auth_secret}
            if "auth_secret" in self.model_fields_set and auth_secret is not None
            else {}
        ) | ({"metadata": self.metadata} if "metadata" in self.model_fields_set else {})


@router.post("/api/model-profiles", status_code=201, response_model=AgentModelProfileEntry)
async def create_model_profile(
    request: Request,
    body: CreateModelProfileRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentModelProfileEntry:
    org_id = identity_value(request, body, "org_id", body.org_id, "x-aithru-org-id")
    try:
        if deps.runtime.model_profile_registry.get_profile(org_id, body.key) is not None:
            raise ModelProfileConflictError(f"Model profile already exists: {body.key}")
        auth_secret = _resolve_model_profile_secret(
            body.auth_secret,
            deps=deps,
            org_id=org_id,
            key=body.key,
        )
        return deps.runtime.model_profile_registry.create_profile(
            body.to_profile(org_id=org_id, auth_secret=auth_secret)
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
        existing = deps.runtime.model_profile_registry.get_profile(
            resolved_org_id,
            profile_id_or_key,
        )
        if existing is None:
            raise ModelProfileNotFoundError(
                f"Model profile not found: {profile_id_or_key}"
            )
        auth_secret = (
            _resolve_model_profile_secret(
                body.auth_secret,
                deps=deps,
                org_id=resolved_org_id,
                key=existing.key,
            )
            if "auth_secret" in body.model_fields_set
            else None
        )
        return deps.runtime.model_profile_registry.update_profile(
            resolved_org_id,
            profile_id_or_key,
            body.registry_updates(auth_secret=auth_secret),
        )
    except ModelProfileNotFoundError as err:
        raise HTTPException(status_code=404, detail="Model profile not found") from err
    except ModelProfileError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


def _resolve_model_profile_secret(
    secret: ModelProfileSecretInput | None,
    *,
    deps: ApiDependencies,
    org_id: str,
    key: str,
) -> AgentModelProfileSecretStatus | None:
    if secret is None:
        return None
    if secret.secret_ref is not None and secret.write_only_value is not None:
        raise ModelProfileError("provide either secret_ref or write_only_value, not both")
    if secret.write_only_value is not None:
        if not isinstance(secret.write_only_value, str) or not secret.write_only_value.strip():
            raise ModelProfileError("write_only_value must be a nonblank string")
        secret_ref = model_profile_api_key_secret_ref(org_id=org_id, key=key)
        try:
            deps.runtime.secret_store.set_secret(secret_ref, secret.write_only_value)
            return AgentModelProfileSecretStatus(
                has_secret=True,
                secret_ref=secret_ref,
                redacted=True,
            )
        except ValueError as err:
            raise ModelProfileError(str(err)) from err
    if secret.secret_ref is not None:
        secret_ref = secret.secret_ref.strip()
        if not secret_ref:
            raise ModelProfileError("secret_ref cannot be blank")
        try:
            return AgentModelProfileSecretStatus(
                has_secret=True,
                secret_ref=secret_ref,
                redacted=True,
            )
        except ValueError as err:
            raise ModelProfileError(str(err)) from err
    return AgentModelProfileSecretStatus()


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
