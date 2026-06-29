from aithru_agent.agent.tools.recovery import recovery_attempt_from_events
from aithru_agent.stream import AgentStreamEvent, AgentStreamSource


def _event(sequence: int, attempt_key: str) -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"run_1:{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp="2026-06-29T00:00:00Z",
        type="tool.recovery.offered",
        source=AgentStreamSource(kind="tool"),
        payload={"attempt_key": attempt_key},
    )


def test_recovery_attempt_from_events_counts_matching_attempt_key() -> None:
    events = [
        _event(1, "workspace.write_file:workspace_path_policy"),
        _event(2, "local.recoverable:invalid_value"),
    ]

    assert recovery_attempt_from_events(
        events=events,
        attempt_key="workspace.write_file:workspace_path_policy",
    ) == 2
