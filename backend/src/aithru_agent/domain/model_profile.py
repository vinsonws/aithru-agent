from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel
from .run import AgentModelCapabilities


class AgentModelProviderKind(StrEnum):
    TEST = "test"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"


class AgentModelProfileCostPolicy(AithruBaseModel):
    input_cost_per_million_tokens_usd: float | None = Field(default=None, ge=0)
    output_cost_per_million_tokens_usd: float | None = Field(default=None, ge=0)
    max_run_cost_usd: float | None = Field(default=None, ge=0)


class AgentModelProfileSelectionPolicy(AithruBaseModel):
    required_scopes: list[str] = Field(default_factory=list)
    max_total_tokens: int | None = Field(default=None, ge=1)

    @field_validator("required_scopes")
    @classmethod
    def _required_scopes_must_not_be_blank(cls, value: list[str]) -> list[str]:
        scopes = [scope.strip() for scope in value]
        if any(not scope for scope in scopes):
            raise ValueError("model profile required scopes cannot contain blank values")
        return sorted(set(scopes))


class AgentModelProfileSecretStatus(AithruBaseModel):
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
    def _secret_status_must_be_consistent(self) -> "AgentModelProfileSecretStatus":
        if self.has_secret and self.secret_ref is None:
            raise ValueError("secret_ref is required when has_secret is true")
        if self.secret_ref is not None:
            self.has_secret = True
            self.redacted = True
        if not self.has_secret:
            self.redacted = False
        return self


class AgentModelProfileDefinition(AithruBaseModel):
    org_id: str
    key: str
    name: str
    provider: AgentModelProviderKind
    model: str
    enabled: bool = True
    capabilities: AgentModelCapabilities = Field(default_factory=AgentModelCapabilities)
    cost_policy: AgentModelProfileCostPolicy = Field(
        default_factory=AgentModelProfileCostPolicy
    )
    selection_policy: AgentModelProfileSelectionPolicy = Field(
        default_factory=AgentModelProfileSelectionPolicy
    )
    auth_secret: AgentModelProfileSecretStatus | None = None
    metadata: dict | None = None

    @field_validator("org_id", "name", "model")
    @classmethod
    def _identity_fields_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("model profile identity fields cannot be blank")
        return stripped

    @field_validator("key")
    @classmethod
    def _key_must_be_slug(cls, value: str) -> str:
        return _slug(value, label="model profile key")

    @field_validator("metadata")
    @classmethod
    def _metadata_must_not_include_secret_material(cls, value: dict | None) -> dict | None:
        if value is None:
            return None
        for key in value:
            normalized = key.strip().lower()
            if _metadata_key_may_contain_secret(normalized):
                raise ValueError("model profile metadata cannot include secret values")
        return value


class AgentModelProfileEntry(AgentModelProfileDefinition):
    id: str
    created_at: str
    updated_at: str


class AgentModelProfileEnablementResult(AithruBaseModel):
    id: str
    org_id: str
    key: str
    enabled: bool
    profile: AgentModelProfileEntry


def _slug(value: str, *, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} cannot be blank")
    allowed = all(char.isalnum() or char in {"_", "-"} for char in stripped)
    if not allowed or " " in stripped:
        raise ValueError(f"{label} must contain only letters, numbers, underscores, or hyphens")
    return stripped


def _validate_secret_ref(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme != "secret" or not parts.netloc:
        raise ValueError("secret_ref must be a secret:// reference")
    if parts.username is not None or parts.password is not None:
        raise ValueError("secret_ref cannot include user info")
    if parts.query or parts.fragment:
        raise ValueError("secret_ref cannot include query or fragment values")


def _metadata_key_may_contain_secret(key: str) -> bool:
    if "secret" in key or "api_key" in key:
        return True
    if "token" not in key:
        return False
    return key not in {"max_tokens", "max_output_tokens", "max_total_tokens"}
