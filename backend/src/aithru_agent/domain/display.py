from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel


AgentPresentationResourceKind = Literal[
    "workspace_file",
    "approval",
    "todo",
    "run",
    "trace_span",
    "external_url",
    "none",
]
AgentPresentationStatus = Literal["pending", "ready", "failed", "dismissed"]
AgentPresentationPriority = Literal["low", "normal", "high"]
AgentPresentationView = Literal[
    "html_preview",
    "source_text",
    "markdown",
    "json",
    "image",
    "pdf",
    "diff",
    "approval_review",
    "activity_detail",
    "download",
    "open_external",
    "none",
]
AgentPresentationSurface = Literal[
    "conversation",
    "side_panel",
    "approval_panel",
    "activity",
    "header",
]
AgentPresentationEffectKind = Literal[
    "open_panel",
    "focus_presentation",
    "scroll_to",
    "highlight",
    "none",
]
AgentPresentationEffectMode = Literal["soft", "assertive"]
AgentPresentationActionKind = Literal[
    "open_view",
    "download",
    "approve",
    "reject",
    "retry",
    "continue",
    "open_in_workbench",
    "open_external",
    "copy_reference",
    "none",
]
AgentPresentationCreatedBy = Literal["harness", "tool", "model_request"]


class AgentPresentationResource(AithruBaseModel):
    kind: AgentPresentationResourceKind
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
    def _resource_has_required_reference(self) -> "AgentPresentationResource":
        if self.kind == "workspace_file" and self.path is None:
            raise ValueError("workspace file presentation resources require path")
        if self.kind in {"approval", "todo", "run", "trace_span"} and self.id is None:
            raise ValueError(f"{self.kind} presentation resources require id")
        if self.kind == "external_url" and self.url is None:
            raise ValueError("external url presentation resources require url")
        return self


class AgentPresentationEffect(AithruBaseModel):
    kind: AgentPresentationEffectKind
    panel: str | None = None
    surface: AgentPresentationSurface | None = None
    presentation_id: str | None = None
    mode: AgentPresentationEffectMode = "soft"

    @model_validator(mode="after")
    def _effect_has_required_target(self) -> "AgentPresentationEffect":
        if self.kind == "open_panel" and self.panel is None:
            raise ValueError("open_panel presentation effects require panel")
        if self.kind in {"focus_presentation", "scroll_to", "highlight"} and self.presentation_id is None:
            raise ValueError(f"{self.kind} presentation effects require presentation_id")
        return self


class AgentPresentationAction(AithruBaseModel):
    kind: AgentPresentationActionKind
    label: str
    view: AgentPresentationView | None = None
    path: str | None = None
    method: Literal["GET", "POST"] | None = None
    requires_confirmation: bool = False


class AgentPresentationSource(AithruBaseModel):
    created_by: AgentPresentationCreatedBy
    event_id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


class AgentPresentation(AithruBaseModel):
    id: str = Field(min_length=1)
    org_id: str | None = None
    thread_id: str | None = None
    run_id: str = Field(min_length=1)
    sequence: int | None = Field(default=None, ge=0)
    status: AgentPresentationStatus = "ready"
    priority: AgentPresentationPriority = "normal"
    title: str = Field(min_length=1)
    summary: str | None = None
    reason: str | None = None
    resource: AgentPresentationResource = Field(default_factory=lambda: AgentPresentationResource(kind="none"))
    surfaces: list[AgentPresentationSurface] = Field(default_factory=lambda: ["conversation"], min_length=1)
    preferred_view: AgentPresentationView = "none"
    available_views: list[AgentPresentationView] = Field(default_factory=lambda: ["none"], min_length=1)
    effects: list[AgentPresentationEffect] = Field(default_factory=list)
    actions: list[AgentPresentationAction] = Field(default_factory=list)
    source: AgentPresentationSource
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("presentation title cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _preferred_view_must_be_available(self) -> "AgentPresentation":
        if self.preferred_view not in self.available_views:
            raise ValueError("preferred view must be in available views")
        return self
