from aithru_agent.capabilities.recovery import (
    nonrecoverable_tool_result,
    recoverable_tool_result,
)
from aithru_agent.domain import AgentToolFailureKind, AgentToolRecoveryAction


def test_recoverable_tool_result_builds_failed_result_with_recovery() -> None:
    result = recoverable_tool_result(
        status="denied",
        kind=AgentToolFailureKind.INVALID_INPUT,
        action=AgentToolRecoveryAction.RETRY_WITH_CORRECTED_INPUT,
        message="Path is outside allowed workspace paths.",
        model_guidance="Use an absolute workspace path under /artifacts.",
        suggested_input={"path": "/artifacts/index.html"},
        allowed_values={"allowed_paths": ["/artifacts"]},
        attempt_key="workspace_path_policy",
        max_attempts=2,
    )

    assert result.status == "denied"
    assert result.error == {"message": "Path is outside allowed workspace paths."}
    assert result.recovery is not None
    assert result.recovery.recoverable is True
    assert result.recovery.kind == AgentToolFailureKind.INVALID_INPUT
    assert result.recovery.action == AgentToolRecoveryAction.RETRY_WITH_CORRECTED_INPUT
    assert result.recovery.suggested_input == {"path": "/artifacts/index.html"}
    assert result.redaction == "none"


def test_nonrecoverable_tool_result_builds_policy_denied_result() -> None:
    result = nonrecoverable_tool_result(
        status="denied",
        kind=AgentToolFailureKind.POLICY_DENIED,
        message="Missing required scope: agent.workspace.write",
    )

    assert result.status == "denied"
    assert result.error == {"message": "Missing required scope: agent.workspace.write"}
    assert result.recovery is not None
    assert result.recovery.recoverable is False
    assert result.recovery.kind == AgentToolFailureKind.POLICY_DENIED
    assert result.recovery.action == AgentToolRecoveryAction.FAIL_RUN
