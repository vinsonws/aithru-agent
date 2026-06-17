from typing import Literal

from .base import AithruBaseModel


AgentMessageRole = Literal["user", "assistant", "system", "tool"]


class AgentMessage(AithruBaseModel):
    id: str
    thread_id: str
    role: AgentMessageRole
    content: str
    run_id: str | None = None
    artifact_ids: list[str] = []
    created_at: str

