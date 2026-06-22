from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel


AgentContextSummarySource = Literal["semantic_processor", "manual", "import"]


class AgentContextSummary(AithruBaseModel):
    id: str
    org_id: str
    thread_id: str | None = None
    run_id: str | None = None
    summary: str = Field(min_length=1)
    source: AgentContextSummarySource
    source_sequence: int | None = Field(default=None, ge=0)
    message_count: int = Field(default=0, ge=0)
    token_estimate: int | None = Field(default=None, ge=0)
    created_at: str

    @field_validator("id", "org_id", "summary", "created_at")
    @classmethod
    def _required_strings_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("context summary strings cannot be blank")
        return stripped

    @field_validator("thread_id", "run_id")
    @classmethod
    def _optional_strings_must_be_meaningful(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _must_identify_thread_or_run(self) -> Self:
        if self.thread_id is None and self.run_id is None:
            raise ValueError("context summary must reference a thread or run")
        return self
