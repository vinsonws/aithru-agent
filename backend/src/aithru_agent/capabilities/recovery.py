from typing import Literal

from aithru_agent.domain import (
    AgentToolCallResult,
    AgentToolFailureKind,
    AgentToolRecovery,
    AgentToolRecoveryAction,
)


ToolFailureStatus = Literal["failed", "denied"]


def recoverable_tool_result(
    *,
    status: ToolFailureStatus,
    kind: AgentToolFailureKind,
    action: AgentToolRecoveryAction,
    message: str,
    model_guidance: str | None = None,
    suggested_input: object | None = None,
    allowed_values: dict[str, object] | None = None,
    retry_after_ms: int | None = None,
    attempt_key: str | None = None,
    max_attempts: int = 2,
    error: dict | None = None,
    redaction: Literal["none", "partial", "full"] = "none",
) -> AgentToolCallResult:
    return AgentToolCallResult(
        status=status,
        error=error or {"message": message},
        recovery=AgentToolRecovery(
            recoverable=True,
            kind=kind,
            action=action,
            message=message,
            model_guidance=model_guidance,
            suggested_input=suggested_input,
            allowed_values=allowed_values,
            retry_after_ms=retry_after_ms,
            attempt_key=attempt_key,
            max_attempts=max_attempts,
        ),
        redaction=redaction,
    )


def nonrecoverable_tool_result(
    *,
    status: ToolFailureStatus,
    kind: AgentToolFailureKind,
    message: str,
    action: AgentToolRecoveryAction = AgentToolRecoveryAction.FAIL_RUN,
    error: dict | None = None,
    redaction: Literal["none", "partial", "full"] = "none",
) -> AgentToolCallResult:
    return AgentToolCallResult(
        status=status,
        error=error or {"message": message},
        recovery=AgentToolRecovery(
            recoverable=False,
            kind=kind,
            action=action,
            message=message,
        ),
        redaction=redaction,
    )
