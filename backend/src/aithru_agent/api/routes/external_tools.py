"""External tool configuration routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, model_validator

from aithru_agent.api.dependencies import ApiDependencies, api_deps, identity_query_value
from aithru_agent.domain import (
    AgentExternalToolCatalogTool,
    AgentExternalToolConfigDefinition,
    AgentExternalToolConfigEntry,
    AgentExternalToolConfigOperationResult,
    AgentExternalToolConfigResetResult,
    AgentExternalToolEndpointConfig,
    AgentExternalToolHTTPProviderConfig,
    AgentExternalToolMCPServerConfig,
    AgentExternalToolProviderKind,
    AgentExternalToolSecretStatus,
    AgentExternalToolWebProviderConfig,
)
from aithru_agent.external_tools import (
    ExternalToolConfigConflictError,
    ExternalToolConfigError,
    ExternalToolConfigNotFoundError,
)

router = APIRouter()


class ExternalToolSecretInput(BaseModel):
    secret_ref: str | None = None
    write_only_value: object | None = Field(
        default=None,
        description="Reserved for a future capability-bound secret store.",
        json_schema_extra={"writeOnly": True},
    )

    def to_secret_status(self, *, org_id: str, key: str) -> AgentExternalToolSecretStatus:
        del org_id, key
        if self.secret_ref is not None and self.write_only_value is not None:
            raise ExternalToolConfigError("provide either secret_ref or write_only_value, not both")
        if self.write_only_value is not None:
            if isinstance(self.write_only_value, str) and not self.write_only_value.strip():
                raise ExternalToolConfigError("write_only_value cannot be blank")
            raise ExternalToolConfigError(
                "write_only_value requires a configured secret store; provide secret_ref"
            )
        if self.secret_ref is not None:
            secret_ref = self.secret_ref.strip()
            if not secret_ref:
                raise ExternalToolConfigError("secret_ref cannot be blank")
            _validate_secret_ref(secret_ref)
            return AgentExternalToolSecretStatus(
                has_secret=True,
                secret_ref=secret_ref,
                redacted=True,
            )
        return AgentExternalToolSecretStatus()


class ExternalToolEndpointConfigRequest(BaseModel):
    url: str
    allowed_hosts: list[str]
    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    max_response_bytes: int = Field(default=100_000, ge=1, le=1_000_000)
    auth_secret: ExternalToolSecretInput | None = None

    def to_endpoint_config(self, *, org_id: str, key: str) -> AgentExternalToolEndpointConfig:
        return AgentExternalToolEndpointConfig(
            url=self.url,
            allowed_hosts=self.allowed_hosts,
            timeout_ms=self.timeout_ms,
            max_response_bytes=self.max_response_bytes,
            auth_secret=(
                self.auth_secret.to_secret_status(org_id=org_id, key=key)
                if self.auth_secret is not None
                else None
            ),
        )


class ExternalToolMCPServerConfigRequest(BaseModel):
    server_key: str = Field(min_length=1)
    name: str | None = None
    endpoint: ExternalToolEndpointConfigRequest
    tools: list[AgentExternalToolCatalogTool] = Field(min_length=1)

    def to_mcp_config(self, *, org_id: str, key: str) -> AgentExternalToolMCPServerConfig:
        return AgentExternalToolMCPServerConfig(
            server_key=self.server_key,
            name=self.name,
            endpoint=self.endpoint.to_endpoint_config(org_id=org_id, key=key),
            tools=self.tools,
        )


class ExternalToolHTTPProviderConfigRequest(BaseModel):
    endpoint: ExternalToolEndpointConfigRequest
    tools: list[AgentExternalToolCatalogTool] = Field(min_length=1)

    def to_http_config(self, *, org_id: str, key: str) -> AgentExternalToolHTTPProviderConfig:
        return AgentExternalToolHTTPProviderConfig(
            endpoint=self.endpoint.to_endpoint_config(org_id=org_id, key=key),
            tools=self.tools,
        )


class ExternalToolWebProviderConfigRequest(BaseModel):
    allowed_hosts: list[str]
    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    max_fetch_bytes: int = Field(default=100_000, ge=1, le=1_000_000)
    search_endpoint: ExternalToolEndpointConfigRequest | None = None

    def to_web_config(self, *, org_id: str, key: str) -> AgentExternalToolWebProviderConfig:
        return AgentExternalToolWebProviderConfig(
            allowed_hosts=self.allowed_hosts,
            timeout_ms=self.timeout_ms,
            max_fetch_bytes=self.max_fetch_bytes,
            search_endpoint=(
                self.search_endpoint.to_endpoint_config(org_id=org_id, key=key)
                if self.search_endpoint is not None
                else None
            ),
        )


class CreateExternalToolConfigRequest(BaseModel):
    org_id: str = "org_1"
    key: str = Field(min_length=1)
    provider_kind: AgentExternalToolProviderKind
    name: str | None = None
    enabled: bool = True
    mcp: ExternalToolMCPServerConfigRequest | None = None
    http: ExternalToolHTTPProviderConfigRequest | None = None
    web: ExternalToolWebProviderConfigRequest | None = None

    def to_definition(self, *, org_id: str) -> AgentExternalToolConfigDefinition:
        return AgentExternalToolConfigDefinition(
            org_id=org_id,
            key=self.key,
            provider_kind=self.provider_kind,
            name=self.name,
            enabled=self.enabled,
            mcp=(
                self.mcp.to_mcp_config(org_id=org_id, key=self.key)
                if self.mcp is not None
                else None
            ),
            http=(
                self.http.to_http_config(org_id=org_id, key=self.key)
                if self.http is not None
                else None
            ),
            web=(
                self.web.to_web_config(org_id=org_id, key=self.key)
                if self.web is not None
                else None
            ),
        )


class UpdateExternalToolConfigRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    mcp: ExternalToolMCPServerConfigRequest | None = None
    http: ExternalToolHTTPProviderConfigRequest | None = None
    web: ExternalToolWebProviderConfigRequest | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateExternalToolConfigRequest":
        if not self.model_fields_set.intersection({"name", "enabled", "mcp", "http", "web"}):
            raise ValueError("at least one external tool config field must be supplied")
        for field in ("name", "mcp", "http", "web"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    def registry_updates(
        self,
        *,
        existing: AgentExternalToolConfigEntry,
    ) -> dict[str, object]:
        updates: dict[str, object] = {}
        if "name" in self.model_fields_set:
            updates["name"] = self.name
        if "enabled" in self.model_fields_set:
            updates["enabled"] = self.enabled
        if "mcp" in self.model_fields_set and self.mcp is not None:
            updates["mcp"] = self.mcp.to_mcp_config(org_id=existing.org_id, key=existing.key)
        if "http" in self.model_fields_set and self.http is not None:
            updates["http"] = self.http.to_http_config(org_id=existing.org_id, key=existing.key)
        if "web" in self.model_fields_set and self.web is not None:
            updates["web"] = self.web.to_web_config(org_id=existing.org_id, key=existing.key)
        return updates


@router.get(
    "/api/external-tools/configs",
    response_model=list[AgentExternalToolConfigEntry],
)
async def list_external_tool_configs(
    request: Request,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentExternalToolConfigEntry]:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    return deps.runtime.external_tool_config_registry.list_configs(resolved_org_id)


@router.post(
    "/api/external-tools/configs",
    status_code=201,
    response_model=AgentExternalToolConfigEntry,
)
async def create_external_tool_config(
    request: Request,
    body: CreateExternalToolConfigRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentExternalToolConfigEntry:
    resolved_org_id = identity_query_value(
        request,
        body.org_id if "org_id" in body.model_fields_set else None,
        body.org_id,
        "x-aithru-org-id",
    )
    try:
        definition = body.to_definition(org_id=resolved_org_id)
        return deps.runtime.external_tool_config_registry.create_config(
            definition,
            actor_user_id=_actor_user_id(request),
        )
    except ExternalToolConfigConflictError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except ValidationError as err:
        raise HTTPException(status_code=422, detail="Invalid external tool config") from err
    except ExternalToolConfigError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


@router.get(
    "/api/external-tools/configs/{config_id_or_key}",
    response_model=AgentExternalToolConfigEntry,
)
async def get_external_tool_config(
    request: Request,
    config_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentExternalToolConfigEntry:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    entry = deps.runtime.external_tool_config_registry.get_config(
        resolved_org_id,
        config_id_or_key,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="External tool config not found")
    return entry


@router.patch(
    "/api/external-tools/configs/{config_id_or_key}",
    response_model=AgentExternalToolConfigEntry,
)
async def update_external_tool_config(
    request: Request,
    config_id_or_key: str,
    body: UpdateExternalToolConfigRequest,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentExternalToolConfigEntry:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    existing = deps.runtime.external_tool_config_registry.get_config(
        resolved_org_id,
        config_id_or_key,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="External tool config not found")
    try:
        updates = body.registry_updates(existing=existing)
        return deps.runtime.external_tool_config_registry.update_config(
            resolved_org_id,
            config_id_or_key,
            updates,
            actor_user_id=_actor_user_id(request),
        )
    except ExternalToolConfigNotFoundError as err:
        raise HTTPException(status_code=404, detail="External tool config not found") from err
    except ValidationError as err:
        raise HTTPException(status_code=422, detail="Invalid external tool config") from err
    except ExternalToolConfigError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


@router.post(
    "/api/external-tools/configs/{config_id_or_key}/enable",
    response_model=AgentExternalToolConfigOperationResult,
)
async def enable_external_tool_config(
    request: Request,
    config_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentExternalToolConfigOperationResult:
    return _set_external_tool_config_enabled(
        request,
        config_id_or_key,
        org_id=org_id,
        enabled=True,
        deps=deps,
    )


@router.post(
    "/api/external-tools/configs/{config_id_or_key}/disable",
    response_model=AgentExternalToolConfigOperationResult,
)
async def disable_external_tool_config(
    request: Request,
    config_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentExternalToolConfigOperationResult:
    return _set_external_tool_config_enabled(
        request,
        config_id_or_key,
        org_id=org_id,
        enabled=False,
        deps=deps,
    )


@router.post(
    "/api/external-tools/configs/{config_id_or_key}/reset-cache",
    response_model=AgentExternalToolConfigResetResult,
)
async def reset_external_tool_config_cache(
    request: Request,
    config_id_or_key: str,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentExternalToolConfigResetResult:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    try:
        return deps.runtime.external_tool_config_registry.reset_cache(
            resolved_org_id,
            config_id_or_key,
            actor_user_id=_actor_user_id(request),
        )
    except ExternalToolConfigNotFoundError as err:
        raise HTTPException(status_code=404, detail="External tool config not found") from err


def _set_external_tool_config_enabled(
    request: Request,
    config_id_or_key: str,
    *,
    org_id: str | None,
    enabled: bool,
    deps: ApiDependencies,
) -> AgentExternalToolConfigOperationResult:
    resolved_org_id = identity_query_value(request, org_id, "org_1", "x-aithru-org-id")
    try:
        return deps.runtime.external_tool_config_registry.set_enabled(
            resolved_org_id,
            config_id_or_key,
            enabled,
            actor_user_id=_actor_user_id(request),
        )
    except ExternalToolConfigNotFoundError as err:
        raise HTTPException(status_code=404, detail="External tool config not found") from err


def _actor_user_id(request: Request) -> str:
    return request.headers.get("x-aithru-user-id") or "user_1"


def _validate_secret_ref(value: str) -> None:
    if not value.startswith("secret://"):
        raise ExternalToolConfigError("secret_ref must be a secret:// reference")
