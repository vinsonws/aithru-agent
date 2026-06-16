from typing import Literal

from .base import AithruBaseModel


class AgentMemoryEntry(AithruBaseModel):
    id: str
    org_id: str
    scope: Literal["thread", "workspace", "project", "user", "organization", "skill"]
    key: str
    value: str
    scope_id: str | None = None
    owner: str | None = None
    source: str | None = None
    confidence: float | None = None
    visibility: Literal["private", "shared", "org"] | None = None
    retention: str | None = None
    created_at: str
    updated_at: str

