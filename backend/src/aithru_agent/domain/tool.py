from enum import StrEnum
from typing import Literal

from .base import AithruBaseModel
from .governance import AgentAuthorizationDecision, AgentCapabilityAuditEvent


class AgentToolKind(StrEnum):
    LOCAL_TOOL = "local_tool"
    EXTERNAL_TOOL = "external_tool"
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


class AgentToolFailurePolicy(StrEnum):
    FAIL_RUN = "fail_run"
    RETURN_RECOVERABLE = "return_recoverable"


class AgentToolFailureKind(StrEnum):
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    TRANSIENT = "transient"
    EXECUTION_FAILED = "execution_failed"
    AMBIGUOUS_INPUT = "ambiguous_input"
    POLICY_DENIED = "policy_denied"
    APPROVAL_REQUIRED = "approval_required"
    FATAL_SYSTEM = "fatal_system"


class AgentToolRecoveryAction(StrEnum):
    RETURN_TO_MODEL = "return_to_model"
    RETRY_WITH_CORRECTED_INPUT = "retry_with_corrected_input"
    USE_ALTERNATIVE_TOOL = "use_alternative_tool"
    ASK_USER = "ask_user"
    WAIT_OR_DEGRADE = "wait_or_degrade"
    REQUIRE_APPROVAL = "require_approval"
    FAIL_RUN = "fail_run"


class AgentToolRecovery(AithruBaseModel):
    recoverable: bool
    kind: AgentToolFailureKind
    action: AgentToolRecoveryAction
    message: str
    model_guidance: str | None = None
    suggested_input: object | None = None
    allowed_values: dict[str, object] | None = None
    retry_after_ms: int | None = None
    attempt_key: str | None = None
    max_attempts: int = 2


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
    failure_policy: AgentToolFailurePolicy | Literal["fail_run", "return_recoverable"] = (
        AgentToolFailurePolicy.FAIL_RUN
    )


class AgentToolCallRequest(AithruBaseModel):
    id: str
    tool_name: str
    input: object
    requested_by: Literal["model", "harness", "subagent", "user", "system"]
    already_approved: bool = False


class AgentToolCallResult(AithruBaseModel):
    status: Literal["completed", "failed", "denied", "waiting_approval", "running"]
    output: object | None = None
    error: dict | None = None
    redaction: Literal["none", "partial", "full"]
    recovery: AgentToolRecovery | None = None
    external_run: AgentExternalRunRef | None = None
    approval_id: str | None = None
    authorization: AgentAuthorizationDecision | None = None
    audit: AgentCapabilityAuditEvent | None = None
