from typing import Any

from aithru_agent.domain import AgentToolCallResult, AgentToolRecovery
from aithru_agent.stream import AgentStreamEvent


def recovery_attempt_key(tool_name: str, recovery: AgentToolRecovery) -> str:
    suffix = recovery.attempt_key or recovery.kind.value
    return f"{tool_name}:{suffix}"


def recovery_event_payload(recovery: AgentToolRecovery) -> dict[str, object]:
    return recovery.model_dump(mode="json")


def model_visible_recovery_payload(
    *,
    tool_name: str,
    result: AgentToolCallResult,
) -> dict[str, object]:
    recovery = result.recovery
    if recovery is None:
        raise ValueError("recoverable payload requires result.recovery")
    payload: dict[str, object] = {
        "status": result.status,
        "recoverable": recovery.recoverable,
        "tool_name": tool_name,
        "failure_kind": recovery.kind.value,
        "message": recovery.message,
    }
    if recovery.model_guidance is not None:
        payload["guidance"] = recovery.model_guidance
    if recovery.suggested_input is not None:
        payload["suggested_input"] = recovery.suggested_input
    if recovery.allowed_values is not None:
        payload["allowed_values"] = recovery.allowed_values
    if recovery.retry_after_ms is not None:
        payload["retry_after_ms"] = recovery.retry_after_ms
    return payload


def recovery_attempt_from_events(
    *,
    events: list[AgentStreamEvent],
    attempt_key: str,
) -> int:
    prior = [
        event
        for event in events
        if event.type == "tool.recovery.offered"
        and isinstance(event.payload, dict)
        and event.payload.get("attempt_key") == attempt_key
    ]
    return len(prior) + 1


def recovery_attempt_payload(
    *,
    tool_name: str,
    recovery: AgentToolRecovery,
    attempt: int,
) -> dict[str, Any]:
    attempt_key = recovery_attempt_key(tool_name, recovery)
    return {
        "attempt_key": attempt_key,
        "attempt": attempt,
        "max_attempts": recovery.max_attempts,
        "failure_kind": recovery.kind.value,
        "action": recovery.action.value,
    }
