from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel


AgentDisplayCardSurface = Literal["conversation", "side_panel", "both"]
AgentDisplayCardType = Literal[
    "file",
    "artifact",
    "approval",
    "todo",
    "memory",
    "search_result",
    "generic",
]
AgentDisplayCardStatus = Literal["pending", "ready", "failed"]
AgentDisplayCardResourceKind = Literal["workspace_file", "artifact", "external_url", "none"]
AgentDisplayCardActionKind = Literal["preview", "download", "open", "none"]
AgentDisplayCardCreatedBy = Literal["harness", "tool", "model_request"]


class AgentDisplayCardResource(AithruBaseModel):
    kind: AgentDisplayCardResourceKind
    id: str | None = None
    path: str | None = None
    url: str | None = None

    @field_validator("id", "path", "url")
    @classmethod
    def _blank_strings_are_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _resource_has_required_reference(self) -> "AgentDisplayCardResource":
        if self.kind == "workspace_file" and self.path is None:
            raise ValueError("workspace file display card resources require path")
        if self.kind == "artifact" and self.id is None:
            raise ValueError("artifact display card resources require id")
        if self.kind == "external_url" and self.url is None:
            raise ValueError("external url display card resources require url")
        return self


class AgentDisplayCardAction(AithruBaseModel):
    kind: AgentDisplayCardActionKind
    label: str | None = None
    target: str | None = None
    disabled: bool = False


class AgentDisplayCardSource(AithruBaseModel):
    created_by: AgentDisplayCardCreatedBy
    event_id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


class AgentDisplayCard(AithruBaseModel):
    id: str = Field(min_length=1)
    thread_id: str | None = None
    run_id: str = Field(min_length=1)
    sequence: int | None = Field(default=None, ge=0)
    surface: AgentDisplayCardSurface = "conversation"
    type: AgentDisplayCardType = "generic"
    status: AgentDisplayCardStatus = "ready"
    title: str = Field(min_length=1)
    summary: str | None = None
    resource: AgentDisplayCardResource = Field(default_factory=lambda: AgentDisplayCardResource(kind="none"))
    actions: list[AgentDisplayCardAction] = Field(default_factory=list)
    source: AgentDisplayCardSource
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("display card title cannot be blank")
        return stripped
