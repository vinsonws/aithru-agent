from aithru_agent.api.snapshots import build_research_continuation_snapshot
from aithru_agent.domain import (
    AgentArtifact,
    AgentRun,
    AgentRunStatus,
    AgentTodo,
    AgentTodoStatus,
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
        goal="Continue research.",
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


def report_artifact(
    *,
    report_status: str,
    source_count: int,
    evidence_count: int,
    limitation_count: int,
) -> AgentArtifact:
    return AgentArtifact(
        id="artifact_report",
        org_id="org_1",
        workspace_id="workspace_1",
        run_id="run_1",
        type="report",
        name="Continuation report",
        uri="/reports/continuation.md",
        metadata={
            "generated_by": "research.create_report",
            "report_status": report_status,
            "source_count": source_count,
            "source_input_count": source_count,
            "duplicate_source_count": 0,
            "evidence_count": evidence_count,
            "limitation_count": limitation_count,
            "quality_summary": {"high": source_count, "medium": 0, "low": 0},
        },
        created_at="2026-06-19T00:01:00Z",
    )


def complete_report() -> dict:
    return {
        "title": "Continuation report",
        "query": "aithru continuation",
        "status": "complete",
        "summary": "One strong source supports the answer.",
        "source_input_count": 1,
        "duplicate_source_count": 0,
        "quality_summary": {"high": 1, "medium": 0, "low": 0},
        "limitations": [],
        "findings": ["Aithru continuation is evidence-backed."],
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
        "markdown": "# Continuation report\n",
    }


def insufficient_report() -> dict:
    return {
        "title": "Continuation report",
        "query": "aithru continuation",
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
        "markdown": "# Continuation report\n",
    }


def test_research_continuation_snapshot_is_ready_for_complete_report() -> None:
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
                        "query": "aithru continuation",
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
                "output": {"report": complete_report(), "artifact": {"id": "artifact_report"}},
            },
        ),
    ]
    snapshot = build_research_continuation_snapshot(
        run=run(),
        events=events,
        todos=[],
        artifacts=[
            report_artifact(
                report_status="complete",
                source_count=1,
                evidence_count=1,
                limitation_count=0,
            )
        ],
        trace=project_trace_spans(events),
    ).model_dump(mode="json")

    assert snapshot["run_id"] == "run_1"
    assert snapshot["status"] == "ready"
    assert snapshot["ready_for_answer"] is True
    assert snapshot["review_status"] == "pass"
    assert snapshot["report_status"] == "complete"
    assert snapshot["query"] == "aithru continuation"
    assert snapshot["reviewed_event_sequence"] == 2
    assert snapshot["counts"] == {
        "action_count": 0,
        "high_priority_action_count": 0,
        "suggested_tool_count": 0,
        "target_section_count": 0,
    }
    assert snapshot["actions"] == []


def test_research_continuation_snapshot_suggests_research_repairs() -> None:
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
                        "query": "aithru continuation",
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
                "query": "aithru continuation",
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
                "output": {"report": insufficient_report(), "artifact": {"id": "artifact_report"}},
            },
        ),
    ]
    snapshot = build_research_continuation_snapshot(
        run=run(),
        events=events,
        todos=todos,
        artifacts=[
            report_artifact(
                report_status="insufficient_evidence",
                source_count=0,
                evidence_count=0,
                limitation_count=2,
            )
        ],
        trace=project_trace_spans(events),
    ).model_dump(mode="json")

    assert snapshot["status"] == "needs_research"
    assert snapshot["ready_for_answer"] is False
    assert snapshot["review_status"] == "fail"
    assert snapshot["report_status"] == "insufficient_evidence"
    assert snapshot["query"] == "aithru continuation"
    assert snapshot["reviewed_event_sequence"] == 3
    assert snapshot["counts"] == {
        "action_count": 4,
        "high_priority_action_count": 3,
        "suggested_tool_count": 3,
        "target_section_count": 0,
    }
    assert [action["kind"] for action in snapshot["actions"]] == [
        "collect_more_sources",
        "retry_search",
        "address_limitations",
        "regenerate_report",
    ]
    assert snapshot["actions"][0]["priority"] == "high"
    assert snapshot["actions"][0]["suggested_tool_names"] == ["web.search", "web.fetch"]
    assert snapshot["actions"][0]["related_finding_codes"] == [
        "insufficient_evidence_report",
        "missing_evidence",
    ]
    assert snapshot["actions"][1]["suggested_research_phases"] == ["search"]
    assert snapshot["actions"][2]["priority"] == "high"
    assert snapshot["actions"][3]["suggested_tool_names"] == ["research.create_report"]


def test_research_continuation_snapshot_targets_missing_report_sections() -> None:
    report = complete_report()
    report["status"] = "partial"
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
        {"section_id": "architecture", "source_count": 1, "evidence_count": 1}
    ]
    report["evidence"][0]["section_id"] = "architecture"
    report["sources"][0]["section_id"] = "architecture"
    events = [
        event(
            1,
            "tool.completed",
            {
                "tool_call_id": "report",
                "tool_name": "research.create_report",
                "status": "completed",
                "output": {"report": report, "artifact": {"id": "artifact_report"}},
            },
        )
    ]

    snapshot = build_research_continuation_snapshot(
        run=run(),
        events=events,
        todos=[],
        artifacts=[],
        trace=project_trace_spans(events),
    ).model_dump(mode="json")

    assert snapshot["status"] == "needs_research"
    assert snapshot["counts"]["target_section_count"] == 1
    assert snapshot["actions"][0]["kind"] == "collect_more_sources"
    assert snapshot["actions"][0]["target_section_ids"] == ["gaps"]
    assert "gaps" in snapshot["actions"][0]["reason"]
    assert snapshot["actions"][1]["kind"] == "regenerate_report"
    assert snapshot["actions"][1]["target_section_ids"] == ["gaps"]


def test_research_continuation_snapshot_targets_weak_quality_sections() -> None:
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
                "output": {"report": report, "artifact": {"id": "artifact_report"}},
            },
        )
    ]

    snapshot = build_research_continuation_snapshot(
        run=run(),
        events=events,
        todos=[],
        artifacts=[
            report_artifact(
                report_status="complete",
                source_count=2,
                evidence_count=2,
                limitation_count=0,
            )
        ],
        trace=project_trace_spans(events),
    ).model_dump(mode="json")

    assert snapshot["status"] == "needs_research"
    assert snapshot["review_status"] == "warn"
    assert snapshot["counts"] == {
        "action_count": 2,
        "high_priority_action_count": 0,
        "suggested_tool_count": 3,
        "target_section_count": 1,
    }
    assert [action["kind"] for action in snapshot["actions"]] == [
        "improve_source_quality",
        "regenerate_report",
    ]
    assert snapshot["actions"][0]["related_finding_codes"] == ["weak_research_sections"]
    assert snapshot["actions"][0]["target_section_ids"] == ["gaps"]
    assert "gaps" in snapshot["actions"][0]["reason"]
    assert snapshot["actions"][1]["target_section_ids"] == ["gaps"]
