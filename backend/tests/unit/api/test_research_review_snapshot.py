from __future__ import annotations

from aithru_agent.api.snapshots import build_research_review_snapshot
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
        task_msg="Review research quality.",
        workspace_id="workspace_1",
        status=AgentRunStatus.COMPLETED,
        started_at="2026-06-19T00:00:00Z",
        completed_at="2026-06-19T00:01:00Z",
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


def report_file(
    *,
    report_status: str,
    source_count: int,
    evidence_count: int,
    limitation_count: int,
) -> AgentWorkspaceFile:
    del report_status, source_count, evidence_count, limitation_count
    return AgentWorkspaceFile(
        workspace_id="workspace_1",
        path="/reports/review.md",
        size=25,
        media_type="text/markdown",
        version=1,
        file_version=1,
        content_hash="hash_review",
        created_at="2026-06-19T00:01:00Z",
        updated_at="2026-06-19T00:01:00Z",
    )


def complete_report() -> dict:
    return {
        "title": "Research review report",
        "query": "aithru review",
        "status": "complete",
        "summary": "One high-quality source supports the answer.",
        "source_input_count": 1,
        "duplicate_source_count": 0,
        "quality_summary": {"high": 1, "medium": 0, "low": 0},
        "limitations": [],
        "findings": ["Aithru review is evidence-backed."],
        "evidence": [
            {
                "citation_number": 1,
                "title": "Aithru Agent",
                "url": "https://example.com/aithru",
                "snippet": "Evidence-backed harness.",
                "excerpt": "Fetched detail.",
                "source": "example-search",
                "published_at": "2026-06-19",
                "quality": {
                    "label": "high",
                    "score": 100,
                    "reasons": [
                        "valid_http_source",
                        "has_search_snippet",
                        "has_fetched_content",
                        "has_provider",
                        "has_published_date",
                    ],
                },
            }
        ],
        "sources": [
            {
                "title": "Aithru Agent",
                "url": "https://example.com/aithru",
                "snippet": "Evidence-backed harness.",
                "content": "Fetched detail.",
                "source": "example-search",
                "published_at": "2026-06-19",
            }
        ],
        "markdown": "# Research review report\n",
    }


def insufficient_report() -> dict:
    return {
        "title": "Research review report",
        "query": "aithru review",
        "status": "insufficient_evidence",
        "summary": "The report could not collect enough evidence.",
        "source_input_count": 0,
        "duplicate_source_count": 0,
        "quality_summary": {"high": 0, "medium": 0, "low": 0},
        "limitations": [
            {
                "code": "research_search_blocked",
                "severity": "warning",
                "message": "Search was blocked.",
            },
            {
                "code": "research_evidence_missing",
                "severity": "error",
                "message": "No usable evidence was collected.",
            },
        ],
        "findings": [],
        "evidence": [],
        "sources": [],
        "markdown": "# Research review report\n",
    }


def test_research_review_snapshot_passes_complete_evidence_report() -> None:
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
                        "query": "aithru review",
                        "objective": "Review report quality.",
                        "steps": [
                            {"phase": "search", "title": "Search sources"},
                            {"phase": "report", "title": "Create research report"},
                        ],
                    },
                    "todos": [],
                },
            },
        ),
        event(
            2,
            "tool.completed",
            {
                "tool_call_id": "report",
                "tool_name": "research.create_report",
                "status": "completed",
                "output": {"report": complete_report(), "workspace_file": {"path": "/reports/review.md"}},
            },
        ),
    ]
    snapshot = build_research_review_snapshot(
        run=run(),
        events=events,
        todos=[],
        workspace_files=[
            report_file(
                report_status="complete",
                source_count=1,
                evidence_count=1,
                limitation_count=0,
            )
        ],
        trace=project_trace_spans(events),
    ).model_dump(mode="json")

    assert snapshot["run_id"] == "run_1"
    assert snapshot["status"] == "pass"
    assert snapshot["score"] == 100
    assert snapshot["ready_for_answer"] is True
    assert snapshot["report_status"] == "complete"
    assert snapshot["reviewed_event_sequence"] == 2
    assert snapshot["counts"] == {
        "source_count": 1,
        "evidence_count": 1,
        "limitation_count": 0,
        "report_file_count": 1,
        "blocked_step_count": 0,
        "web_failure_count": 0,
        "high_quality_source_count": 1,
        "low_quality_source_count": 0,
        "weak_section_count": 0,
        "finding_count": 0,
    }
    assert snapshot["findings"] == []


def test_research_review_snapshot_fails_insufficient_evidence_report() -> None:
    todos = [
        todo("todo_search", "Search sources", AgentTodoStatus.BLOCKED, 1),
        todo("todo_report", "Create research report", AgentTodoStatus.DONE, 2),
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
                        "query": "aithru review",
                        "objective": "Review report quality.",
                        "steps": [
                            {"phase": "search", "title": "Search sources"},
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
                "query": "aithru review",
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
                "output": {"report": insufficient_report(), "workspace_file": {"path": "/reports/review.md"}},
            },
        ),
    ]
    snapshot = build_research_review_snapshot(
        run=run(),
        events=events,
        todos=todos,
        workspace_files=[
            report_file(
                report_status="insufficient_evidence",
                source_count=0,
                evidence_count=0,
                limitation_count=2,
            )
        ],
        trace=project_trace_spans(events),
    ).model_dump(mode="json")

    assert snapshot["status"] == "fail"
    assert snapshot["score"] == 0
    assert snapshot["ready_for_answer"] is False
    assert snapshot["report_status"] == "insufficient_evidence"
    assert snapshot["counts"] == {
        "source_count": 0,
        "evidence_count": 0,
        "limitation_count": 2,
        "report_file_count": 1,
        "blocked_step_count": 1,
        "web_failure_count": 1,
        "high_quality_source_count": 0,
        "low_quality_source_count": 0,
        "weak_section_count": 0,
        "finding_count": 5,
    }
    assert [finding["code"] for finding in snapshot["findings"]] == [
        "insufficient_evidence_report",
        "missing_evidence",
        "blocked_research_steps",
        "web_failures",
        "research_limitations",
    ]
    assert {finding["severity"] for finding in snapshot["findings"]} == {"error", "warning"}


def test_research_review_snapshot_warns_for_weak_report_sections() -> None:
    report = complete_report()
    report["summary"] = "Architecture is strong, but gaps need stronger evidence."
    report["source_input_count"] = 2
    report["quality_summary"] = {"high": 1, "medium": 1, "low": 0}
    report["sections"] = [
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
    ]
    report["section_summary"] = [
        {"section_id": "architecture", "source_count": 1, "evidence_count": 1},
        {"section_id": "gaps", "source_count": 1, "evidence_count": 1},
    ]
    report["evidence"][0]["section_id"] = "architecture"
    report["sources"][0]["section_id"] = "architecture"
    report["evidence"].append(
        {
            "citation_number": 2,
            "title": "Aithru Gaps",
            "url": "https://example.com/aithru-gaps",
            "snippet": "Gaps evidence.",
            "excerpt": None,
            "source": "example-search",
            "published_at": None,
            "section_id": "gaps",
            "quality": {
                "label": "medium",
                "score": 55,
                "reasons": ["valid_http_source", "has_search_snippet"],
            },
        }
    )
    report["sources"].append(
        {
            "title": "Aithru Gaps",
            "url": "https://example.com/aithru-gaps",
            "snippet": "Gaps evidence.",
            "content": None,
            "source": "example-search",
            "published_at": None,
            "section_id": "gaps",
        }
    )
    events = [
        event(
            1,
            "tool.completed",
            {
                "tool_call_id": "report",
                "tool_name": "research.create_report",
                "status": "completed",
                "output": {"report": report, "workspace_file": {"path": "/reports/review.md"}},
            },
        )
    ]

    snapshot = build_research_review_snapshot(
        run=run(),
        events=events,
        todos=[],
        workspace_files=[
            report_file(
                report_status="complete",
                source_count=2,
                evidence_count=2,
                limitation_count=0,
            )
        ],
        trace=project_trace_spans(events),
    ).model_dump(mode="json")

    assert snapshot["status"] == "warn"
    assert snapshot["score"] == 80
    assert snapshot["ready_for_answer"] is False
    assert snapshot["counts"]["high_quality_source_count"] == 1
    assert snapshot["counts"]["weak_section_count"] == 1
    assert [finding["code"] for finding in snapshot["findings"]] == ["weak_research_sections"]
    assert "gaps" in snapshot["findings"][0]["message"]
