from typing import Literal

from .base import AithruBaseModel


AgentArtifactType = Literal[
    "text",
    "markdown",
    "json",
    "decision",
    "report",
    "file",
    "patch",
    "workflow_draft",
]


class AgentArtifact(AithruBaseModel):
    id: str
    org_id: str
    workspace_id: str
    run_id: str | None = None
    type: AgentArtifactType
    name: str
    media_type: str | None = None
    uri: str | None = None
    content: object | None = None
    metadata: dict | None = None
    created_at: str
    finalized_at: str | None = None

