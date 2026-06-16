from enum import StrEnum

from .base import AithruBaseModel


class AgentApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AgentApprovalStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class AgentApproval(AithruBaseModel):
    id: str
    run_id: str
    tool_call_id: str
    tool_name: str
    status: AgentApprovalStatus
    decision: AgentApprovalDecision | None = None
    comment: str | None = None
    created_at: str
    resolved_at: str | None = None

