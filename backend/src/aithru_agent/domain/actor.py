from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel

AgentActorType = Literal["user", "service", "delegated", "system"]


class AgentActorContext(AithruBaseModel):
    actor_type: AgentActorType
    org_id: str
    user_id: str | None = None
    service_id: str | None = None
    delegated_user_id: str | None = None
    scopes: list[str] = Field(default_factory=list)

    @field_validator("org_id", "user_id", "service_id", "delegated_user_id")
    @classmethod
    def _string_ids_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("actor identifiers cannot be blank")
        return stripped

    @field_validator("scopes")
    @classmethod
    def _scopes_must_be_normalized(cls, value: list[str]) -> list[str]:
        return normalize_scope_list(value)

    @model_validator(mode="after")
    def _validate_actor_identifier(self) -> "AgentActorContext":
        if self.actor_type == "user" and self.user_id is None:
            raise ValueError("user actor requires user_id")
        if self.actor_type == "service" and self.service_id is None:
            raise ValueError("service actor requires service_id")
        if self.actor_type == "delegated" and (self.user_id is None or self.service_id is None):
            raise ValueError("delegated actor requires user_id and service_id")
        return self


def normalize_scope_list(value: list[str]) -> list[str]:
    scopes: list[str] = []
    seen: set[str] = set()
    for scope in value:
        stripped = scope.strip()
        if not stripped:
            raise ValueError("scopes cannot contain blank scopes")
        if stripped in seen:
            continue
        seen.add(stripped)
        scopes.append(stripped)
    return scopes
