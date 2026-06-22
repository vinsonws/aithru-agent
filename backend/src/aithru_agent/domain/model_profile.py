from enum import StrEnum

from pydantic import Field, field_validator

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
