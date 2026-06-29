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


def test_projects_run_model_tool_approval_and_workspace_spans() -> None:
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
                    "result_summary": {
                        "content": "Done",
                        "content_truncated": False,
                        "workspace_paths": ["/reports/child.md"],
                        "workspace_files": [],
                        "workspace_file_count": 1,
                        "has_output": True,
                    },
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
        "workspace_file_count": 1,
        "workspace_paths": ["/reports/child.md"],
        "result_content_length": 4,
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


def test_projects_web_search_and_fetch_spans() -> None:
    spans = project_trace_spans(
        [
            ev(
                1,
                "web.search.completed",
                {
                    "tool_call_id": "tc_search",
                    "query": "aithru",
                    "result_count": 1,
                },
                "web",
            ),
            ev(
                2,
                "web.fetch.completed",
                {
                    "tool_call_id": "tc_fetch",
                    "url": "https://example.com/aithru",
                    "status_code": 200,
                    "content_length": 42,
                    "truncated": False,
                },
                "web",
            ),
        ]
    )

    by_id = {span.id: span for span in spans}

    assert by_id["web:tc_search"].kind == "web"
    assert by_id["web:tc_search"].name == "web.search"
    assert by_id["web:tc_search"].status == "completed"
    assert by_id["web:tc_search"].refs == {
        "tool_call_id": "tc_search",
        "query": "aithru",
        "result_count": 1,
    }
    assert by_id["web:tc_fetch"].kind == "web"
    assert by_id["web:tc_fetch"].name == "web.fetch"
    assert by_id["web:tc_fetch"].status == "completed"
    assert by_id["web:tc_fetch"].refs == {
        "tool_call_id": "tc_fetch",
        "url": "https://example.com/aithru",
        "status_code": 200,
        "content_length": 42,
        "truncated": False,
    }


def test_projects_external_run_span() -> None:
    spans = project_trace_spans(
        [
            ev(
                1,
                "external_run.created",
                {
                    "kind": "workflow_capability",
                    "tool_call_id": "tc_workflow",
                    "tool_name": "workflow.report_review",
                    "capability_key": "report_review",
                    "capability_run_id": "caprun_1",
                    "status": "running",
                    "correlation_id": "run_1:tc_workflow",
                    "approval_id": None,
                },
                "workflow",
            ),
            ev(
                2,
                "external_approval.requested",
                {
                    "kind": "workflow_capability",
                    "capability_run_id": "caprun_1",
                    "approval_id": "capapproval_1",
                },
                "workflow",
            ),
            ev(
                3,
                "external_run.completed",
                {
                    "kind": "workflow_capability",
                    "tool_call_id": "tc_workflow",
                    "tool_name": "workflow.report_review",
                    "capability_key": "report_review",
                    "capability_run_id": "caprun_1",
                    "status": "completed",
                    "correlation_id": "run_1:tc_workflow",
                    "approval_id": "capapproval_1",
                },
                "workflow",
            ),
        ]
    )

    by_id = {span.id: span for span in spans}

    assert by_id["external_run:caprun_1"].kind == "external_run"
    assert by_id["external_run:caprun_1"].name == "workflow.report_review"
    assert by_id["external_run:caprun_1"].status == "completed"
    assert by_id["external_run:caprun_1"].refs == {
        "kind": "workflow_capability",
        "tool_call_id": "tc_workflow",
        "tool_name": "workflow.report_review",
        "capability_key": "report_review",
        "capability_run_id": "caprun_1",
        "correlation_id": "run_1:tc_workflow",
        "approval_id": "capapproval_1",
    }


def test_projects_failed_web_search_and_fetch_spans() -> None:
    spans = project_trace_spans(
        [
            ev(
                1,
                "web.search.failed",
                {
                    "tool_call_id": "tc_search",
                    "query": "aithru",
                    "error": {"message": "search provider unavailable"},
                    "limitation": {
                        "code": "web_search_failed",
                        "severity": "warning",
                        "message": "Controlled web search failed: search provider unavailable.",
                        "source_url": None,
                    },
                },
                "web",
            ),
            ev(
                2,
                "web.fetch.failed",
                {
                    "tool_call_id": "tc_fetch",
                    "url": "https://example.com/aithru",
                    "error": {"message": "fetch provider unavailable"},
                    "limitation": {
                        "code": "web_fetch_failed",
                        "severity": "warning",
                        "message": "Controlled web fetch failed: fetch provider unavailable.",
                        "source_url": "https://example.com/aithru",
                    },
                },
                "web",
            ),
        ]
    )

    by_id = {span.id: span for span in spans}

    assert by_id["web:tc_search"].kind == "web"
    assert by_id["web:tc_search"].name == "web.search"
    assert by_id["web:tc_search"].status == "failed"
    assert by_id["web:tc_search"].refs == {
        "tool_call_id": "tc_search",
        "query": "aithru",
        "error": {"message": "search provider unavailable"},
        "limitation": {
            "code": "web_search_failed",
            "severity": "warning",
            "message": "Controlled web search failed: search provider unavailable.",
            "source_url": None,
        },
    }
    assert by_id["web:tc_fetch"].kind == "web"
    assert by_id["web:tc_fetch"].name == "web.fetch"
    assert by_id["web:tc_fetch"].status == "failed"
    assert by_id["web:tc_fetch"].refs == {
        "tool_call_id": "tc_fetch",
        "url": "https://example.com/aithru",
        "error": {"message": "fetch provider unavailable"},
        "limitation": {
            "code": "web_fetch_failed",
            "severity": "warning",
            "message": "Controlled web fetch failed: fetch provider unavailable.",
            "source_url": "https://example.com/aithru",
        },
    }


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
