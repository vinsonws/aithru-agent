from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel


class WorkbenchWorkflowDraft(AithruBaseModel):
    draft_kind: Literal["workbench_workflow_draft"] = "workbench_workflow_draft"
    executable: bool = False
    title: str
    summary: str
    source_run_id: str
    source_workspace_id: str
    source_thread_id: str | None = None
    suggested_steps: list[str] = Field(min_length=1)
    required_inputs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    handoff_notes: str | None = None

    @field_validator(
        "title",
        "summary",
        "source_run_id",
        "source_workspace_id",
        "source_thread_id",
        "handoff_notes",
    )
    @classmethod
    def _optional_string_must_be_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Workbench draft strings cannot be blank")
        return stripped

    @field_validator("suggested_steps", "required_inputs", "risks", "open_questions")
    @classmethod
    def _list_items_must_be_non_blank(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("Workbench draft list items cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def _draft_must_not_be_executable(self) -> "WorkbenchWorkflowDraft":
        if self.executable:
            raise ValueError("Workbench workflow drafts are not executable Agent workflows")
        return self
