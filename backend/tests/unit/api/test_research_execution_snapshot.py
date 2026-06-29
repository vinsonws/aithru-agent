from __future__ import annotations

from aithru_agent.api.snapshots import build_research_execution_snapshot
from aithru_agent.domain import (    AgentRun,
    AgentRunStatus,
    AgentTodo,
    AgentTodoStatus,
    AgentWorkspaceFile,
)
from aithru_agent.stream.events import AgentStreamEvent
from aithru_agent.trace import project_trace_spans


def run() -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        skill_id="deep-research",
        task_msg="Research Aithru parity.",
        workspace_id="workspace_1",
        status=AgentRunStatus.COMPLETED,
        started_at="2026-06-19T00:00:00Z",
        completed_at="2026-06-19T00:01:00Z",
    )


def todo(
    todo_id: str,
    title: str,
    status: AgentTodoStatus,
    order: int,
) -> AgentTodo:
    return AgentTodo(
        id=todo_id,
        run_id="run_1",
        title=title,
        status=status,
        created_by="agent",
        order=order,
    )


def report_file() -> AgentWorkspaceFile:
    return AgentWorkspaceFile(
        workspace_id="workspace_1",
        path="/reports/aithru-parity.md",
        size=24,
        media_type="text/markdown",
        version=1,
        file_version=1,
        content_hash="hash_report",
        created_at="2026-06-19T00:01:00Z",
        updated_at="2026-06-19T00:01:00Z",
    )


def event(sequence: int, event_type: str, payload: dict) -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"event_{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp="2026-06-19T00:00:00Z",
        type=event_type,
        source={"kind": "test"},
        payload=payload,
    )


def test_research_execution_snapshot_projects_plan_steps_and_progress() -> None:
    todos = [
        todo("todo_search", "Search sources", AgentTodoStatus.BLOCKED, 1),
        todo("todo_fetch", "Fetch and review sources", AgentTodoStatus.PENDING, 2),
        todo("todo_synth", "Synthesize findings", AgentTodoStatus.DONE, 3),
        todo("todo_report", "Create research report", AgentTodoStatus.DONE, 4),
    ]
    events = [
        event(
            1,
            "tool.completed",
            {
                "tool_call_id": "plan",
                "tool_name": "research.create_plan",
                "status": "completed",
                "output": {
                    "plan": {
                        "query": "aithru deerflow parity",
                        "objective": "Compare backend progress.",
                        "sections": [
                            {
                                "section_id": "architecture",
                                "title": "Architecture",
                                "question": "How is the backend structured?",
                                "priority": "high",
                            },
                            {
                                "section_id": "gaps",
                                "title": "Open gaps",
                                "question": "What remains incomplete?",
                                "priority": "medium",
                            },
                        ],
                        "steps": [
                            {"phase": "search", "title": "Search sources"},
                            {"phase": "fetch", "title": "Fetch and review sources"},
                            {"phase": "synthesize", "title": "Synthesize findings"},
                            {"phase": "report", "title": "Create research report"},
                        ],
                    },
                    "todos": [item.model_dump(mode="json") for item in todos],
                },
            },
        ),
        event(
            2,
            "web.search.failed",
            {
                "tool_call_id": "search",
                "query": "aithru deerflow parity",
                "error": {"message": "search unavailable"},
                "limitation": {
                    "code": "web_search_failed",
                    "severity": "warning",
                    "message": "Controlled web search failed.",
                },
            },
        ),
        event(
            3,
            "tool.completed",
            {
                "tool_call_id": "report",
                "tool_name": "research.create_report",
                "status": "completed",
                "output": {
                    "report": {
                        "title": "Aithru parity report",
                        "query": "aithru deerflow parity",
                        "status": "insufficient_evidence",
                        "summary": "Search was blocked.",
                        "source_input_count": 0,
                        "duplicate_source_count": 0,
                        "quality_summary": {"high": 0, "medium": 0, "low": 0},
                        "sections": [],
                        "section_summary": [],
                        "limitations": [
                            {
                                "code": "research_search_blocked",
                                "severity": "warning",
                                "message": "Search was blocked.",
                            }
                        ],
                        "findings": [],
                        "evidence": [],
                        "sources": [],
                        "markdown": "# Aithru parity report\n",
                    },
                    "workspace_file": {"path": "/reports/aithru-parity.md"},
                },
            },
        ),
    ]

    snapshot = build_research_execution_snapshot(
        run=run(),
        events=events,
        todos=todos,
        workspace_files=[report_file()],
        trace=project_trace_spans(events),
    ).model_dump(mode="json")

    assert snapshot["run_id"] == "run_1"
    assert snapshot["status"] == "degraded"
    assert snapshot["degraded"] is True
    assert snapshot["plan"] == {
        "query": "aithru deerflow parity",
        "objective": "Compare backend progress.",
        "sections": [
            {
                "section_id": "architecture",
                "title": "Architecture",
                "question": "How is the backend structured?",
                "priority": "high",
            },
            {
                "section_id": "gaps",
                "title": "Open gaps",
                "question": "What remains incomplete?",
                "priority": "medium",
            },
        ],
        "source_event_sequence": 1,
    }
    assert [(step["phase"], step["title"], step["status"]) for step in snapshot["steps"]] == [
        ("search", "Search sources", "blocked"),
        ("fetch", "Fetch and review sources", "pending"),
        ("synthesize", "Synthesize findings", "done"),
        ("report", "Create research report", "done"),
    ]
    assert snapshot["steps"][0]["attention"] is True
    assert snapshot["steps"][0]["web_failure_count"] == 1
    assert set(snapshot["steps"][0]["limitation_codes"]) == {
        "web_search_failed",
        "research_search_blocked",
    }
    assert snapshot["steps"][3]["report_workspace_paths"] == ["/reports/aithru-parity.md"]
    assert snapshot["progress"] == {
        "total_steps": 4,
        "pending_steps": 1,
        "running_steps": 0,
        "done_steps": 2,
        "blocked_steps": 1,
        "cancelled_steps": 0,
        "terminal_steps": 3,
        "web_success_count": 0,
        "web_failure_count": 1,
        "report_file_count": 1,
        "limitation_count": 2,
    }
    assert snapshot["summary"]["status"] == "insufficient_evidence"
