from aithru_agent.domain import AgentRun, AgentRunStatus, AgentRunSource
from aithru_agent.stream.display_cards import (
    display_cards_for_tool_result,
    display_cards_from_events,
)
from aithru_agent.stream.events import AgentStreamEvent, AgentStreamSource


def run() -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        thread_id="thread_1",
        actor_user_id="user_1",
        source="api",
        task_msg="write file",
        status="running",
        workspace_id="ws_1",
        scopes=["*"],
        started_at="2026-06-25T00:00:00Z",
    )


def event(sequence: int, payload: dict, *, type: str = "display.card.created") -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"run_1:{sequence}",
        run_id="run_1",
        thread_id="thread_1",
        sequence=sequence,
        timestamp="2026-06-25T00:00:00Z",
        type=type,
        source=AgentStreamSource(kind="harness"),
        payload=payload,
    )


def test_workspace_write_file_result_projects_file_card() -> None:
    cards = display_cards_for_tool_result(
        run(),
        tool_call_id="tool_1",
        tool_name="workspace.write_file",
        output={
            "workspace_id": "ws_1",
            "path": "/a.txt",
            "size": 12,
            "media_type": "text/plain",
        },
    )

    assert len(cards) == 1
    card = cards[0]
    assert card.type == "file"
    assert card.title == "a.txt"
    assert card.resource.kind == "workspace_file"
    assert card.resource.path == "/a.txt"
    assert card.source.tool_call_id == "tool_1"
    assert card.source.tool_name == "workspace.write_file"
    assert card.actions[0].kind == "preview"


def test_artifact_result_projects_artifact_card() -> None:
    cards = display_cards_for_tool_result(
        run(),
        tool_call_id="tool_2",
        tool_name="artifact.create",
        output={
            "id": "artifact_1",
            "name": "report.md",
            "type": "markdown",
            "media_type": "text/markdown",
        },
    )

    assert len(cards) == 1
    assert cards[0].type == "artifact"
    assert cards[0].resource.kind == "artifact"
    assert cards[0].resource.id == "artifact_1"


def test_sandbox_write_file_result_projects_file_card() -> None:
    cards = display_cards_for_tool_result(
        run(),
        tool_call_id="tool_sandbox_write",
        tool_name="sandbox.write_file",
        output={
            "workspace_id": "ws_1",
            "path": "/sandbox.txt",
            "size": 24,
            "media_type": "text/plain",
        },
    )

    assert len(cards) == 1
    assert cards[0].type == "file"
    assert cards[0].resource.kind == "workspace_file"
    assert cards[0].resource.path == "/sandbox.txt"
    assert cards[0].source.tool_name == "sandbox.write_file"


def test_sandbox_promote_file_result_projects_artifact_card() -> None:
    cards = display_cards_for_tool_result(
        run(),
        tool_call_id="tool_promote",
        tool_name="sandbox.promote_file",
        output={
            "path": "/reports/summary.md",
            "artifact": {
                "id": "artifact_sandbox_1",
                "name": "Sandbox Summary",
                "type": "report",
                "media_type": "text/markdown",
            },
        },
    )

    assert len(cards) == 1
    assert cards[0].type == "artifact"
    assert cards[0].resource.kind == "artifact"
    assert cards[0].resource.id == "artifact_sandbox_1"
    assert cards[0].source.tool_name == "sandbox.promote_file"


def test_display_cards_from_events_fills_sequence_from_event() -> None:
    cards = display_cards_from_events(
        [
            event(
                7,
                {
                    "card": {
                        "id": "card_1",
                        "run_id": "run_1",
                        "thread_id": "thread_1",
                        "surface": "conversation",
                        "type": "file",
                        "status": "ready",
                        "title": "a.txt",
                        "resource": {"kind": "workspace_file", "path": "/a.txt"},
                        "source": {"created_by": "harness", "tool_call_id": "tool_1"},
                    }
                },
            )
        ]
    )

    assert cards[0].sequence == 7


def test_display_card_updates_preserve_created_sequence() -> None:
    cards = display_cards_from_events(
        [
            event(
                7,
                {
                    "card": {
                        "id": "card_1",
                        "run_id": "run_1",
                        "thread_id": "thread_1",
                        "surface": "conversation",
                        "type": "file",
                        "status": "pending",
                        "title": "a.txt",
                        "resource": {"kind": "workspace_file", "path": "/a.txt"},
                        "source": {"created_by": "harness", "tool_call_id": "tool_1"},
                    }
                },
            ),
            event(
                11,
                {
                    "card": {
                        "id": "card_1",
                        "run_id": "run_1",
                        "thread_id": "thread_1",
                        "surface": "conversation",
                        "type": "file",
                        "status": "ready",
                        "title": "a.txt",
                        "resource": {"kind": "workspace_file", "path": "/a.txt"},
                        "source": {"created_by": "harness", "tool_call_id": "tool_1"},
                    }
                },
                type="display.card.updated",
            ),
        ]
    )

    assert len(cards) == 1
    assert cards[0].sequence == 7
    assert cards[0].status == "ready"
