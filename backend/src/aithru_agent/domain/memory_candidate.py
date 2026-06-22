from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel
from .memory import AgentMemoryEntry, AgentMemoryRetentionPolicy, AgentMemoryScope

AgentMemoryCandidateStatus = Literal["pending", "approved", "rejected"]


class AgentMemoryCandidate(AithruBaseModel):
    id: str
    org_id: str
    run_id: str
    scope: AgentMemoryScope
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    status: AgentMemoryCandidateStatus = "pending"
    scope_id: str | None = None
    retention: AgentMemoryRetentionPolicy | None = None
    created_at: str
    resolved_at: str | None = None

    @field_validator("id", "org_id", "run_id", "key", "value", "created_at")
    @classmethod
    def _required_strings_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("memory candidate strings cannot be blank")
        return stripped

    @field_validator("scope_id", "resolved_at")
    @classmethod
    def _optional_strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("memory candidate optional strings cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _pending_candidates_must_not_be_resolved(self) -> "AgentMemoryCandidate":
        if self.status == "pending" and self.resolved_at is not None:
            raise ValueError("pending memory candidates cannot have resolved_at")
        return self


class AgentMemoryCandidateApprovalResult(AithruBaseModel):
    candidate: AgentMemoryCandidate
    memory_entry: AgentMemoryEntry
