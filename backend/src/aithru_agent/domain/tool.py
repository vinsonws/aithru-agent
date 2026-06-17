from enum import StrEnum
from typing import Literal

from .base import AithruBaseModel


class AgentToolKind(StrEnum):
    LOCAL_TOOL = "local_tool"
    WORKFLOW_CAPABILITY = "workflow_capability"


class AgentToolRiskLevel(StrEnum):
    SAFE = "safe"
    READ = "read"
    WRITE = "write"
    DANGEROUS = "dangerous"


class AgentToolApprovalPolicy(StrEnum):
    NEVER = "never"
    ON_RISK = "on_risk"
    ALWAYS = "always"


class AgentExternalRunRef(AithruBaseModel):
    kind: Literal["workflow_capability"]
    capability_key: str
    capability_run_id: str
    status: str
    correlation_id: str | None = None
    approval_id: str | None = None


class AgentToolDescriptor(AithruBaseModel):
    name: str
    kind: AgentToolKind
    description: str
    input_schema: dict
    output_schema: dict
    risk_level: AgentToolRiskLevel
    required_scopes: list[str]
    approval_policy: AgentToolApprovalPolicy | Literal["never", "on_risk", "always"]


class AgentToolCallRequest(AithruBaseModel):
    id: str
    tool_name: str
    input: object
    requested_by: Literal["model", "harness", "subagent", "user", "system"]
    already_approved: bool = False


class AgentToolCallResult(AithruBaseModel):
    status: Literal["completed", "failed", "denied", "waiting_approval"]
    output: object | None = None
    error: dict | None = None
    redaction: Literal["none", "partial", "full"]
    external_run: AgentExternalRunRef | None = None
    approval_id: str | None = None

