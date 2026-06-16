from typing import Literal

from .base import AithruBaseModel


class AgentActorContext(AithruBaseModel):
    actor_type: Literal["user", "service", "delegated", "system"]
    org_id: str
    user_id: str | None = None
    scopes: list[str] = []

