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
    assert available_views_for_file(name="index.html", media_type=None, artifact_type="file") == [
        "html_preview",
        "source_text",
        "download",
    ]


def test_workspace_write_file_result_projects_file_presentation() -> None:
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

    assert len(presentations) == 1
    presentation = presentations[0]
    assert presentation.resource.kind == "workspace_file"
    assert presentation.resource.path == "/a.txt"
    assert presentation.title == "a.txt"
    assert presentation.preferred_view == "source_text"
    assert presentation.available_views == ["source_text", "download"]
    assert presentation.source.tool_name == "workspace.write_file"


def test_artifact_result_projects_html_presentation_from_name() -> None:
    presentations = presentations_for_tool_result(
        run(),
        tool_call_id="tool_2",
        tool_name="artifact.create",
        output={
            "id": "artifact_1",
            "name": "index.html",
            "type": "file",
            "media_type": None,
        },
    )

    assert len(presentations) == 1
    presentation = presentations[0]
    assert presentation.resource.kind == "artifact"
    assert presentation.resource.id == "artifact_1"
    assert presentation.preferred_view == "html_preview"
    assert "source_text" in presentation.available_views
    assert presentation.effects[0].kind == "open_panel"


def test_presentations_from_events_fills_sequence_and_preserves_created_sequence_on_update() -> None:
    created = presentations_for_tool_result(
        run(),
        tool_call_id="tool_1",
        tool_name="workspace.write_file",
        output={"path": "/a.txt", "media_type": "text/plain"},
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
