from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel
from .tool import AgentToolApprovalPolicy, AgentToolFailurePolicy, AgentToolRiskLevel


class AgentExternalToolProviderKind(StrEnum):
    MCP = "mcp"
    HTTP = "http"
    WEB = "web"


class AgentExternalToolActivationStatus(StrEnum):
    CONFIGURED = "configured"
    PENDING_RUNTIME_RELOAD = "pending_runtime_reload"


class AgentExternalToolConfigAuditAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    ENABLED = "enabled"
    DISABLED = "disabled"
    RESET_CACHE = "reset_cache"


class AgentExternalToolOAuthConnectionStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    CONNECTED = "connected"
    EXPIRED = "expired"
    RESET_REQUIRED = "reset_required"


class AgentExternalToolCacheState(StrEnum):
    EMPTY = "empty"
    PRIMED = "primed"
    UNKNOWN = "unknown"


class AgentExternalToolSecretStatus(AithruBaseModel):
    has_secret: bool = False
    secret_ref: str | None = None
    redacted: bool = False

    @field_validator("secret_ref")
    @classmethod
    def _secret_ref_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("secret_ref cannot be blank")
        _validate_secret_ref(stripped)
        return stripped

    @model_validator(mode="after")
    def _secret_status_must_be_consistent(self) -> "AgentExternalToolSecretStatus":
        if self.has_secret and self.secret_ref is None:
            raise ValueError("secret_ref is required when has_secret is true")
        if self.secret_ref is not None:
            self.has_secret = True
            self.redacted = True
        if not self.has_secret:
            self.redacted = False
        return self


class AgentExternalToolEndpointConfig(AithruBaseModel):
    url: str
    allowed_hosts: list[str]
    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    max_response_bytes: int = Field(default=100_000, ge=1, le=1_000_000)
    auth_secret: AgentExternalToolSecretStatus | None = None

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, value: str) -> str:
        url = value.strip()
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            raise ValueError("external tool endpoint must use http or https")
        if parts.hostname is None:
            raise ValueError("external tool endpoint must include a host")
        if parts.username is not None or parts.password is not None:
            raise ValueError("external tool endpoint cannot include user info")
        return url

    @field_validator("allowed_hosts")
    @classmethod
    def _allowed_hosts_must_be_explicit(cls, value: list[str]) -> list[str]:
        hosts = [_normalize_allowed_host(host) for host in value]
        if not hosts:
            raise ValueError("external tool allowed hosts are required")
        if len(set(hosts)) != len(hosts):
            raise ValueError("external tool allowed hosts must be unique")
        return hosts

    @model_validator(mode="after")
    def _endpoint_host_must_be_allowed(self) -> "AgentExternalToolEndpointConfig":
        host = _url_host(self.url)
        if host is None:
            raise ValueError("external tool endpoint must include a host")
        if not _host_allowed(host, self.allowed_hosts):
            raise ValueError(f"external tool endpoint host is not allowed: {host}")
        return self


class AgentExternalToolCatalogTool(AithruBaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict = Field(default_factory=lambda: {"type": "object"})
    risk_level: AgentToolRiskLevel
    required_scopes: list[str] = Field(min_length=1)
    approval_policy: AgentToolApprovalPolicy
    failure_policy: AgentToolFailurePolicy = AgentToolFailurePolicy.FAIL_RUN
    metadata: dict | None = None

    @field_validator("name")
    @classmethod
    def _name_must_be_slug(cls, value: str) -> str:
        return _slug(value, label="external tool name")

    @field_validator("description")
    @classmethod
    def _description_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("external tool description cannot be blank")
        return stripped

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _schema_must_be_object(cls, value: dict) -> dict:
        if value.get("type") != "object":
            raise ValueError("external tool schemas must be JSON object schemas")
        _validate_object_schema(value)
        return value

    @field_validator("required_scopes")
    @classmethod
    def _scopes_must_not_be_blank(cls, value: list[str]) -> list[str]:
        scopes = [scope.strip() for scope in value]
        if any(not scope for scope in scopes):
            raise ValueError("external tool scopes cannot contain blank values")
        return scopes

    @model_validator(mode="after")
    def _risky_tools_must_require_approval(self) -> "AgentExternalToolCatalogTool":
        if (
            self.risk_level in {AgentToolRiskLevel.WRITE, AgentToolRiskLevel.DANGEROUS}
            and self.approval_policy == AgentToolApprovalPolicy.NEVER
        ):
            raise ValueError("write and dangerous external tools must require approval")
        return self


class AgentExternalToolMCPServerConfig(AithruBaseModel):
    server_key: str = Field(min_length=1)
    name: str | None = None
    endpoint: AgentExternalToolEndpointConfig
    tools: list[AgentExternalToolCatalogTool] = Field(min_length=1)

    @field_validator("server_key")
    @classmethod
    def _server_key_must_be_slug(cls, value: str) -> str:
        return _slug(value, label="MCP server key")

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("MCP server name cannot be blank")
        return stripped


class AgentExternalToolHTTPProviderConfig(AithruBaseModel):
    endpoint: AgentExternalToolEndpointConfig
    tools: list[AgentExternalToolCatalogTool] = Field(min_length=1)


class AgentExternalToolWebProviderConfig(AithruBaseModel):
    allowed_hosts: list[str]
    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    max_fetch_bytes: int = Field(default=100_000, ge=1, le=1_000_000)
    search_endpoint: AgentExternalToolEndpointConfig | None = None

    @field_validator("allowed_hosts")
    @classmethod
    def _allowed_hosts_must_be_explicit(cls, value: list[str]) -> list[str]:
        hosts = [_normalize_allowed_host(host) for host in value]
        if not hosts:
            raise ValueError("web external tool allowed hosts are required")
        if len(set(hosts)) != len(hosts):
            raise ValueError("web external tool allowed hosts must be unique")
        return hosts


class AgentExternalToolOAuthStatus(AithruBaseModel):
    status: AgentExternalToolOAuthConnectionStatus = (
        AgentExternalToolOAuthConnectionStatus.NOT_CONFIGURED
    )
    connected: bool = False
    last_error: str | None = None


class AgentExternalToolCacheStatus(AithruBaseModel):
    status: AgentExternalToolCacheState = AgentExternalToolCacheState.EMPTY
    last_reset_at: str | None = None


class AgentExternalToolConfigDefinition(AithruBaseModel):
    org_id: str
    key: str
    provider_kind: AgentExternalToolProviderKind
    name: str | None = None
    enabled: bool = True
    mcp: AgentExternalToolMCPServerConfig | None = None
    http: AgentExternalToolHTTPProviderConfig | None = None
    web: AgentExternalToolWebProviderConfig | None = None

    @field_validator("org_id", "key")
    @classmethod
    def _identity_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("external tool config identity fields cannot be blank")
        return stripped

    @field_validator("key")
    @classmethod
    def _key_must_be_slug(cls, value: str) -> str:
        return _slug(value, label="external tool config key")

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("external tool config name cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _provider_config_must_match_kind(self) -> "AgentExternalToolConfigDefinition":
        configs = {
            AgentExternalToolProviderKind.MCP: self.mcp,
            AgentExternalToolProviderKind.HTTP: self.http,
            AgentExternalToolProviderKind.WEB: self.web,
        }
        expected = configs[self.provider_kind]
        if expected is None:
            raise ValueError(f"{self.provider_kind.value} configuration is required")
        unexpected = [
            kind.value
            for kind, config in configs.items()
            if kind != self.provider_kind and config is not None
        ]
        if unexpected:
            raise ValueError(
                "external tool config cannot include provider settings for: "
                + ", ".join(unexpected)
            )
        return self


class AgentExternalToolConfigAuditEvent(AithruBaseModel):
    action: AgentExternalToolConfigAuditAction
    at: str
    actor_user_id: str


class AgentExternalToolConfigEntry(AgentExternalToolConfigDefinition):
    id: str
    activation_status: AgentExternalToolActivationStatus = (
        AgentExternalToolActivationStatus.PENDING_RUNTIME_RELOAD
    )
    oauth_status: AgentExternalToolOAuthStatus = Field(
        default_factory=AgentExternalToolOAuthStatus
    )
    cache_status: AgentExternalToolCacheStatus = Field(
        default_factory=AgentExternalToolCacheStatus
    )
    created_at: str
    updated_at: str
    created_by: str
    updated_by: str
    audit: list[AgentExternalToolConfigAuditEvent] = Field(default_factory=list)


class AgentExternalToolConfigOperationResult(AithruBaseModel):
    action: AgentExternalToolConfigAuditAction
    config: AgentExternalToolConfigEntry
    audit_event: AgentExternalToolConfigAuditEvent


class AgentExternalToolConfigResetResult(AithruBaseModel):
    id: str
    org_id: str
    key: str
    action: AgentExternalToolConfigAuditAction = AgentExternalToolConfigAuditAction.RESET_CACHE
    reset_at: str
    activation_status: AgentExternalToolActivationStatus
    cache_status: AgentExternalToolCacheStatus
    audit_event: AgentExternalToolConfigAuditEvent
    config: AgentExternalToolConfigEntry


def _normalize_allowed_host(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if not host:
        raise ValueError("external tool allowed hosts cannot contain blank values")
    if any(char.isspace() for char in host) or "/" in host or ":" in host or "*" in host:
        raise ValueError(
            "external tool allowed hosts must be host names without schemes, ports, or wildcards"
        )
    return host


def _url_host(value: str) -> str | None:
    host = urlsplit(value).hostname
    return host.lower().rstrip(".") if host else None


def _host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def _validate_secret_ref(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme != "secret" or not parts.netloc:
        raise ValueError("secret_ref must be a secret:// reference")
    if parts.username is not None or parts.password is not None:
        raise ValueError("secret_ref cannot include user info")
    if parts.query or parts.fragment:
        raise ValueError("secret_ref cannot include query or fragment values")


def _validate_object_schema(value: dict) -> None:
    properties = value.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise ValueError("external tool schema properties must be an object")
    required = value.get("required")
    if required is not None and (
        not isinstance(required, list)
        or any(not isinstance(item, str) or not item.strip() for item in required)
    ):
        raise ValueError("external tool schema required values must be nonblank strings")
    additional_properties = value.get("additionalProperties")
    if additional_properties is not None and not isinstance(
        additional_properties,
        (bool, dict),
    ):
        raise ValueError(
            "external tool schema additionalProperties must be a boolean or object"
        )


def _slug(value: str, *, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} cannot be blank")
    allowed = all(char.isalnum() or char in {"_", "-"} for char in stripped)
    if not allowed or " " in stripped:
        raise ValueError(f"{label} must contain only letters, numbers, underscores, or hyphens")
    return stripped
