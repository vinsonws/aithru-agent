from aithru_agent.domain import AgentRun
from aithru_agent.stream.events import AgentStreamEvent, AgentStreamSource
from aithru_agent.stream.presentations import (
    available_views_for_file,
    presentation_event_payload,
    presentations_for_tool_result,
    presentations_from_events,
)


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
        started_at="2026-06-29T00:00:00Z",
    )


def event(sequence: int, payload: dict, *, type: str = "presentation.created") -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"run_1:{sequence}",
        run_id="run_1",
        thread_id="thread_1",
        sequence=sequence,
        timestamp="2026-06-29T00:00:00Z",
        type=type,
        source=AgentStreamSource(kind="harness"),
        payload=payload,
    )


def test_html_name_resolves_html_preview_even_without_media_type() -> None:
    assert available_views_for_file(name="interactive-demo.html", media_type=None, file_type="file") == [
        "html_preview",
        "source_text",
        "download",
    ]


def test_workspace_write_file_result_does_not_auto_project_presentation() -> None:
    presentations = presentations_for_tool_result(
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

    assert presentations == []


def test_research_report_result_does_not_auto_project_presentation() -> None:
    presentations = presentations_for_tool_result(
        run(),
        tool_call_id="tool_2",
        tool_name="research.create_report",
        output={
            "workspace_id": "ws_1",
            "path": "/reports/research.md",
            "media_type": "text/markdown",
            "size": 42,
        },
    )

    assert presentations == []


def test_presentations_from_events_fills_sequence_and_preserves_created_sequence_on_update() -> None:
    created = presentations_for_tool_result(
        run(),
        tool_call_id="tool_1",
        tool_name="presentation.present",
        output={
            "presentations": [
                {
                    "id": "presentation_1",
                    "run_id": "run_1",
                    "title": "a.txt",
                    "resource": {"kind": "workspace_file", "path": "/a.txt"},
                    "preferred_view": "source_text",
                    "available_views": ["source_text", "download"],
                    "source": {
                        "created_by": "model_request",
                        "tool_call_id": "tool_1",
                        "tool_name": "presentation.present",
                    },
                }
            ]
        },
    )[0]
    updated = created.model_copy(update={"status": "failed"})

    presentations = presentations_from_events(
        [
            event(7, presentation_event_payload(created)),
            event(11, presentation_event_payload(updated), type="presentation.updated"),
        ]
    )

    assert len(presentations) == 1
    assert presentations[0].sequence == 7
    assert presentations[0].status == "failed"
