from enum import StrEnum

from .base import AithruBaseModel


class AgentThreadStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class AgentThread(AithruBaseModel):
    id: str
    org_id: str
    owner_user_id: str
    title: str | None = None
    status: AgentThreadStatus = AgentThreadStatus.ACTIVE
    created_at: str
    updated_at: str

