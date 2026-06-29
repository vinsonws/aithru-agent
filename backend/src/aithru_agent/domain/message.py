from typing import Literal

from pydantic import Field, model_validator

from .base import AithruBaseModel
from .vision import AgentWorkspaceImageAttachment


AgentMessageRole = Literal["user", "assistant", "system", "tool"]


class AgentMessage(AithruBaseModel):
    id: str
    thread_id: str
    role: AgentMessageRole
    content: str
    run_id: str | None = None
    workspace_paths: list[str] = []
    attachments: list[AgentWorkspaceImageAttachment] = Field(default_factory=list)
    created_at: str

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_artifact_ids(cls, value: object) -> object:
        if isinstance(value, dict) and "artifact_ids" in value:
            return {key: item for key, item in value.items() if key != "artifact_ids"}
        return value
