from typing import Literal

from pydantic import Field, field_validator, model_validator

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
AgentArtifactRetentionMode = Literal["ephemeral", "retained", "expires_at"]
AgentArtifactListOrderBy = Literal["created_at", "finalized_at", "name", "type"]
AgentArtifactListOrderDirection = Literal["asc", "desc"]
AgentArtifactDownloadDisposition = Literal["inline", "attachment"]


class AgentArtifactRetentionPolicy(AithruBaseModel):
    mode: AgentArtifactRetentionMode = "retained"
    expires_at: str | None = None
    legal_hold: bool = False

    @model_validator(mode="after")
    def validate_retention(self) -> "AgentArtifactRetentionPolicy":
        if self.mode == "expires_at" and not self.expires_at:
            raise ValueError("expires_at is required when artifact retention mode is expires_at")
        if self.mode != "expires_at" and self.expires_at is not None:
            raise ValueError("expires_at is only valid when artifact retention mode is expires_at")
        if self.mode == "ephemeral" and self.legal_hold:
            raise ValueError("ephemeral artifacts cannot be under legal hold")
        return self


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
    retention: AgentArtifactRetentionPolicy | None = None
    created_at: str
    finalized_at: str | None = None


class AgentArtifactSummary(AithruBaseModel):
    id: str
    type: AgentArtifactType
    name: str
    uri: str | None = None
    media_type: str | None = None
    summary: str | None = None
    truncated: bool = False


class AgentArtifactDownloadInfo(AithruBaseModel):
    artifact_id: str
    filename: str
    media_type: str
    content_length: int = Field(ge=0)
    disposition: AgentArtifactDownloadDisposition
    source_path: str | None = None

    @field_validator("filename")
    @classmethod
    def filename_must_be_safe(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("artifact download filename must not be blank")
        if "/" in stripped or "\\" in stripped:
            raise ValueError("artifact download filename must not contain path separators")
        if any(ord(char) < 32 for char in stripped):
            raise ValueError("artifact download filename must not contain control characters")
        return stripped


class AgentArtifactPromotionResult(AithruBaseModel):
    artifact: AgentArtifact
    workspace_id: str
    path: str
    version: int
    file_version: int
    content_hash: str | None = None


class AgentArtifactListFilters(AithruBaseModel):
    run_id: str | None = None
    workspace_id: str | None = None
    type: AgentArtifactType | None = None
    retention_mode: AgentArtifactRetentionMode | None = None
    finalized: bool | None = None

    @field_validator("run_id", "workspace_id")
    @classmethod
    def non_blank_resource_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("artifact list resource ids must not be blank")
        return stripped


class AgentArtifactListPage(AithruBaseModel):
    items: list[AgentArtifact]
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int | None = Field(default=None, ge=1, le=100)
    offset: int = Field(ge=0)
    order_by: AgentArtifactListOrderBy | None = None
    order_direction: AgentArtifactListOrderDirection
    filters: AgentArtifactListFilters = Field(default_factory=AgentArtifactListFilters)

    @model_validator(mode="after")
    def validate_counts(self) -> "AgentArtifactListPage":
        if self.count != len(self.items):
            raise ValueError("artifact list count must equal number of items")
        if self.total < self.count:
            raise ValueError("artifact list total must be greater than or equal to count")
        return self
