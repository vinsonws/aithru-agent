from aithru_agent.stream import AgentStreamEvent
from aithru_agent.trace import project_trace_spans


def ev(sequence: int, type: str, payload: dict, source_kind: str = "harness") -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"run_1:{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp=f"2026-06-16T00:00:{sequence:02d}Z",
        type=type,
        source={"kind": source_kind},
        payload=payload,
    )


def test_projects_run_model_tool_approval_workspace_and_artifact_spans() -> None:
    spans = project_trace_spans(
        [
            ev(1, "run.created", {"status": "queued"}),
            ev(2, "run.started", {"status": "running"}),
            ev(3, "model.started", {}, "model"),
            ev(4, "tool.started", {"tool_call_id": "tc_1", "tool_name": "workspace.read_file"}, "tool"),
            ev(5, "workspace.file.read", {"path": "/notes.md"}, "workspace"),
            ev(6, "tool.completed", {"tool_call_id": "tc_1", "tool_name": "workspace.read_file"}, "tool"),
            ev(7, "approval.requested", {"approval_id": "appr_1", "tool_call_id": "tc_2"}, "approval"),
            ev(8, "approval.resolved", {"approval_id": "appr_1", "decision": "approved"}, "approval"),
            ev(9, "artifact.created", {"artifact_id": "artifact_1", "name": "Report"}, "artifact"),
            ev(10, "model.completed", {}, "model"),
            ev(11, "run.completed", {"status": "completed"}),
        ]
    )

    by_id = {span.id: span for span in spans}

    assert by_id["run:run_1"].kind == "run"
    assert by_id["run:run_1"].status == "completed"
    assert by_id["model:run_1"].status == "completed"
    assert by_id["tool:tc_1"].name == "workspace.read_file"
    assert by_id["tool:tc_1"].status == "completed"
    assert by_id["approval:appr_1"].status == "completed"
    assert by_id["workspace:run_1:5"].refs == {"path": "/notes.md"}
    assert by_id["artifact:artifact_1"].status == "completed"


def test_failed_run_marks_open_model_span_failed() -> None:
    spans = project_trace_spans(
        [
            ev(1, "run.created", {"status": "queued"}),
            ev(2, "model.started", {}, "model"),
            ev(3, "run.failed", {"error": {"message": "boom"}}),
        ]
    )

    by_id = {span.id: span for span in spans}

    assert by_id["run:run_1"].status == "failed"
    assert by_id["model:run_1"].status == "failed"


def test_projects_model_usage_into_model_span_refs() -> None:
    spans = project_trace_spans(
        [
            ev(1, "run.created", {"status": "queued"}),
            ev(2, "model.started", {}, "model"),
            ev(
                3,
                "model.usage",
                {
                    "input_tokens": 12,
                    "output_tokens": 3,
                    "total_tokens": 15,
                    "requests": 1,
                },
                "model",
            ),
            ev(4, "model.completed", {}, "model"),
        ]
    )

    by_id = {span.id: span for span in spans}

    assert by_id["model:run_1"].refs == {
        "input_tokens": 12,
        "output_tokens": 3,
        "total_tokens": 15,
        "requests": 1,
    }


def test_projects_subagent_span() -> None:
    spans = project_trace_spans(
        [
            ev(1, "run.created", {"status": "queued"}),
            ev(
                2,
                "subagent.started",
                {
                    "subagent_run_id": "subagent_run_1",
                    "child_run_id": "run_2",
                    "name": "researcher",
                },
                "subagent",
            ),
            ev(
                3,
                "subagent.completed",
                {
                    "subagent_run_id": "subagent_run_1",
                    "child_run_id": "run_2",
                    "name": "researcher",
                    "result": "Done",
                },
                "subagent",
            ),
            ev(4, "run.completed", {"status": "completed"}),
        ]
    )

    by_id = {span.id: span for span in spans}

    assert by_id["subagent:subagent_run_1"].kind == "subagent"
    assert by_id["subagent:subagent_run_1"].name == "researcher"
    assert by_id["subagent:subagent_run_1"].status == "completed"
    assert by_id["subagent:subagent_run_1"].refs == {
        "subagent_run_id": "subagent_run_1",
        "child_run_id": "run_2",
    }


def test_projects_memory_spans() -> None:
    spans = project_trace_spans(
        [
            ev(1, "run.created", {"status": "queued"}),
            ev(
                2,
                "memory.written",
                {"operation": "write", "memory_scope": "user", "memory_id": "memory_1"},
                "memory",
            ),
            ev(3, "memory.read", {"operation": "read", "count": 1}, "memory"),
        ]
    )

    memory_spans = [span for span in spans if span.kind == "memory"]

    assert [span.status for span in memory_spans] == ["completed", "completed"]
    assert memory_spans[0].refs == {"operation": "write", "memory_scope": "user"}
    assert memory_spans[1].refs == {"operation": "read", "count": 1}


def test_projects_todo_spans() -> None:
    spans = project_trace_spans(
        [
            ev(
                1,
                "todo.created",
                {"id": "todo_1", "title": "Read files", "status": "running"},
                "harness",
            ),
            ev(
                2,
                "todo.updated",
                {"id": "todo_1", "title": "Read files", "status": "done"},
                "harness",
            ),
        ]
    )

    by_id = {span.id: span for span in spans}

    assert by_id["todo:todo_1"].kind == "todo"
    assert by_id["todo:todo_1"].name == "Read files"
    assert by_id["todo:todo_1"].status == "completed"
    assert by_id["todo:todo_1"].refs == {"todo_id": "todo_1", "status": "done"}


def test_projects_message_span() -> None:
    spans = project_trace_spans(
        [
            ev(1, "message.created", {"message_id": "msg_1", "role": "assistant"}),
            ev(2, "message.delta", {"message_id": "msg_1", "delta": "hello"}),
            ev(3, "message.completed", {"message_id": "msg_1", "content": "hello"}),
        ]
    )

    by_id = {span.id: span for span in spans}

    assert by_id["message:msg_1"].kind == "message"
    assert by_id["message:msg_1"].name == "assistant"
    assert by_id["message:msg_1"].status == "completed"
    assert by_id["message:msg_1"].refs == {"message_id": "msg_1", "role": "assistant"}
