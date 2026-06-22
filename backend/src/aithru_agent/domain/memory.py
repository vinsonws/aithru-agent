from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel

AgentMemoryScope = Literal["thread", "workspace", "project", "user", "organization", "skill"]
AgentMemoryVisibility = Literal["private", "shared", "org"]
AgentMemoryRetentionMode = Literal["ephemeral", "retained", "expires_at"]


class AgentMemoryRetentionPolicy(AithruBaseModel):
    mode: AgentMemoryRetentionMode = "retained"
    expires_at: str | None = None

    @model_validator(mode="after")
    def validate_retention(self) -> "AgentMemoryRetentionPolicy":
        if self.mode == "expires_at" and not self.expires_at:
            raise ValueError("expires_at is required when memory retention mode is expires_at")
        if self.mode != "expires_at" and self.expires_at is not None:
            raise ValueError("expires_at is only valid when memory retention mode is expires_at")
        return self

    def is_expired(self, reference_time: str | None = None) -> bool:
        if self.mode != "expires_at" or self.expires_at is None:
            return False
        reference = _parse_timestamp(reference_time) if reference_time else datetime.now(UTC)
        return _parse_timestamp(self.expires_at) <= reference


class AgentMemoryEntry(AithruBaseModel):
    id: str
    org_id: str
    scope: AgentMemoryScope
    key: str
    value: str
    scope_id: str | None = None
    owner: str | None = None
    source: str | None = None
    confidence: float | None = None
    visibility: AgentMemoryVisibility | None = None
    retention: AgentMemoryRetentionPolicy | None = None
    created_at: str
    updated_at: str

    def is_expired(self, reference_time: str | None = None) -> bool:
        return bool(self.retention and self.retention.is_expired(reference_time))


class AgentMemoryForgetResult(AithruBaseModel):
    memory_id: str
    org_id: str
    forgotten: bool
    deleted_count: int = Field(ge=0)

    @field_validator("memory_id", "org_id")
    @classmethod
    def _ids_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("memory forget result ids cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _forgotten_must_match_deleted_count(self) -> "AgentMemoryForgetResult":
        if self.forgotten != (self.deleted_count > 0):
            raise ValueError("memory forget result forgotten flag must match deleted count")
        return self


class AgentMemoryVisibilityPolicy(AithruBaseModel):
    actor_user_id: str | None = None

    @field_validator("actor_user_id")
    @classmethod
    def _actor_user_id_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("memory visibility actor_user_id cannot be blank")
        return stripped

    def allows(self, entry: AgentMemoryEntry) -> bool:
        if entry.visibility != "private":
            return True
        if self.actor_user_id is None:
            return False
        if entry.owner is not None:
            return entry.owner == self.actor_user_id
        return entry.scope == "user" and entry.scope_id == self.actor_user_id


class AgentMemoryRecallItem(AithruBaseModel):
    memory_id: str
    scope: AgentMemoryScope
    scope_id: str | None = None
    key: str
    value: str
    owner: str | None = None
    source: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    visibility: AgentMemoryVisibility | None = None
    reason: str
    created_at: str
    updated_at: str
    truncated: bool = False
    original_length: int = Field(default=0, ge=0)

    @field_validator("memory_id", "key", "value", "reason", "created_at", "updated_at")
    @classmethod
    def _required_strings_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("memory recall strings cannot be blank")
        return stripped

    @field_validator("scope_id", "owner", "source")
    @classmethod
    def _optional_strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("memory recall optional strings cannot be blank")
        return stripped

    @classmethod
    def from_entry(
        cls,
        entry: AgentMemoryEntry,
        *,
        reason: str,
        max_value_chars: int,
    ) -> "AgentMemoryRecallItem":
        value, truncated, original_length = _bounded_text(entry.value, max_chars=max_value_chars)
        return cls(
            memory_id=entry.id,
            scope=entry.scope,
            scope_id=entry.scope_id,
            key=entry.key,
            value=value,
            owner=entry.owner,
            source=entry.source,
            confidence=entry.confidence,
            visibility=entry.visibility,
            reason=reason,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            truncated=truncated,
            original_length=original_length,
        )


class AgentMemoryRecall(AithruBaseModel):
    run_id: str
    items: list[AgentMemoryRecallItem] = Field(default_factory=list)
    count: int = Field(ge=0)
    dropped: int = Field(default=0, ge=0)

    @field_validator("run_id")
    @classmethod
    def _run_id_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("memory recall run_id cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _count_must_match_items(self) -> "AgentMemoryRecall":
        if self.count != len(self.items):
            raise ValueError("memory recall count must match items")
        return self


def _bounded_text(value: str, *, max_chars: int) -> tuple[str, bool, int]:
    original_length = len(value)
    if original_length <= max_chars:
        return value, False, 0
    return value[:max_chars], True, original_length


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
