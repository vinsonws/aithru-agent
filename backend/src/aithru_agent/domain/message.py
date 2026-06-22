from typing import Literal

from pydantic import Field

from .base import AithruBaseModel
from .vision import AgentWorkspaceImageAttachment


AgentMessageRole = Literal["user", "assistant", "system", "tool"]


class AgentMessage(AithruBaseModel):
    id: str
    thread_id: str
    role: AgentMessageRole
    content: str
    run_id: str | None = None
    artifact_ids: list[str] = []
    attachments: list[AgentWorkspaceImageAttachment] = Field(default_factory=list)
    created_at: str
