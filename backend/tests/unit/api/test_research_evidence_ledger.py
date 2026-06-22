from aithru_agent.api.snapshots import build_research_evidence_ledger
from aithru_agent.domain import AgentArtifact, AgentRun, AgentRunStatus
from aithru_agent.stream.events import AgentStreamEvent


def run() -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        skill_id="deep-research",
        goal="Research evidence.",
        workspace_id="workspace_1",
        status=AgentRunStatus.COMPLETED,
        started_at="2026-06-19T00:00:00Z",
        completed_at="2026-06-19T00:01:00Z",
    )


def event(sequence: int, payload: dict) -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"event_{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp="2026-06-19T00:00:00Z",
        type="tool.completed",
        source={"kind": "tool"},
        payload=payload,
    )


def artifact() -> AgentArtifact:
    return AgentArtifact(
        id="artifact_report",
        org_id="org_1",
        workspace_id="workspace_1",
        run_id="run_1",
        type="report",
        name="Evidence report",
        uri="/reports/evidence.md",
        metadata={
            "generated_by": "research.create_report",
            "report_status": "partial",
            "source_count": 1,
            "source_input_count": 2,
            "duplicate_source_count": 1,
            "evidence_count": 1,
            "limitation_count": 1,
            "section_count": 1,
            "section_summary": [{"section_id": "architecture", "source_count": 1, "evidence_count": 1}],
            "quality_summary": {"high": 1, "medium": 0, "low": 0},
        },
        created_at="2026-06-19T00:01:00Z",
    )


def test_research_evidence_ledger_projects_latest_report_output() -> None:
    report = {
        "title": "Evidence report",
        "query": "aithru evidence",
        "status": "partial",
        "summary": "Collected one high-quality source.",
        "source_input_count": 2,
        "duplicate_source_count": 1,
        "quality_summary": {"high": 1, "medium": 0, "low": 0},
        "limitations": [
            {
                "code": "fetch_partial",
                "severity": "warning",
                "message": "One supporting source could not be fetched.",
                "source_url": "https://example.com/aithru",
            }
        ],
        "findings": ["Aithru Agent: Evidence-backed harness."],
        "evidence": [
            {
                "citation_number": 1,
                "title": "Aithru Agent",
                "url": "https://example.com/aithru",
                "snippet": "Evidence-backed harness.",
                "excerpt": "Fetched detail.",
                "source": "example-search",
                "published_at": "2026-06-18",
                "section_id": "architecture",
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
                "published_at": "2026-06-18",
                "section_id": "architecture",
            }
        ],
        "section_summary": [
            {"section_id": "architecture", "source_count": 1, "evidence_count": 1}
        ],
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
        "markdown": "# Evidence report\n",
    }
    ledger = build_research_evidence_ledger(
        run=run(),
        events=[
            event(
                2,
                {
                    "tool_call_id": "report",
                    "tool_name": "research.create_report",
                    "status": "completed",
                    "output": {
                        "report": report,
                        "artifact": {"id": "artifact_report"},
                    },
                },
            )
        ],
        artifacts=[artifact()],
    ).model_dump(mode="json")

    assert ledger["run_id"] == "run_1"
    assert ledger["status"] == "partial"
    assert ledger["degraded"] is True
    assert ledger["title"] == "Evidence report"
    assert ledger["query"] == "aithru evidence"
    assert ledger["summary"] == "Collected one high-quality source."
    assert ledger["source_event_sequence"] == 2
    assert ledger["quality_summary"] == {"high": 1, "medium": 0, "low": 0}
    assert ledger["counts"] == {
        "source_input_count": 2,
        "duplicate_source_count": 1,
        "source_count": 1,
        "evidence_count": 1,
        "limitation_count": 1,
        "section_count": 2,
        "missing_section_count": 1,
        "weak_section_count": 0,
        "report_artifact_count": 1,
    }
    assert ledger["sections"] == [
        {
            "section_id": "architecture",
            "title": "Architecture",
            "question": "How is the backend structured?",
            "priority": "high",
            "source_count": 1,
            "evidence_count": 1,
            "covered": True,
            "quality_summary": {"high": 1, "medium": 0, "low": 0},
            "weak_quality": False,
        },
        {
            "section_id": "gaps",
            "title": "Open gaps",
            "question": "What remains incomplete?",
            "priority": "medium",
            "source_count": 0,
            "evidence_count": 0,
            "covered": False,
            "quality_summary": {"high": 0, "medium": 0, "low": 0},
            "weak_quality": False,
        },
    ]
    assert ledger["section_summary"] == [
        {"section_id": "architecture", "source_count": 1, "evidence_count": 1}
    ]
    assert ledger["sources"] == report["sources"]
    assert ledger["evidence"] == report["evidence"]
    assert ledger["limitations"] == report["limitations"]
    assert ledger["report_artifacts"] == [
        {
            "artifact_id": "artifact_report",
            "name": "Evidence report",
            "uri": "/reports/evidence.md",
            "report_status": "partial",
            "source_count": 1,
            "source_input_count": 2,
            "duplicate_source_count": 1,
            "evidence_count": 1,
            "limitation_count": 1,
            "section_count": 1,
            "section_summary": [{"section_id": "architecture", "source_count": 1, "evidence_count": 1}],
            "quality_summary": {"high": 1, "medium": 0, "low": 0},
        }
    ]


def test_research_evidence_ledger_projects_weak_section_quality() -> None:
    report = {
        "title": "Evidence report",
        "query": "aithru section quality",
        "status": "complete",
        "summary": "One section is strong and one section needs better evidence.",
        "source_input_count": 2,
        "duplicate_source_count": 0,
        "quality_summary": {"high": 1, "medium": 1, "low": 0},
        "limitations": [],
        "findings": [
            "Architecture is strongly supported.",
            "Gaps are supported by medium-quality evidence.",
        ],
        "evidence": [
            {
                "citation_number": 1,
                "title": "Aithru Architecture",
                "url": "https://example.com/aithru-architecture",
                "snippet": "Architecture evidence.",
                "excerpt": "Fetched architecture detail.",
                "source": "example-search",
                "published_at": "2026-06-18",
                "section_id": "architecture",
                "quality": {
                    "label": "high",
                    "score": 100,
                    "reasons": ["valid_http_source", "has_fetched_content"],
                },
            },
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
            },
        ],
        "sources": [
            {
                "title": "Aithru Architecture",
                "url": "https://example.com/aithru-architecture",
                "snippet": "Architecture evidence.",
                "content": "Fetched architecture detail.",
                "source": "example-search",
                "published_at": "2026-06-18",
                "section_id": "architecture",
            },
            {
                "title": "Aithru Gaps",
                "url": "https://example.com/aithru-gaps",
                "snippet": "Gaps evidence.",
                "content": None,
                "source": "example-search",
                "published_at": None,
                "section_id": "gaps",
            },
        ],
        "section_summary": [
            {"section_id": "architecture", "source_count": 1, "evidence_count": 1},
            {"section_id": "gaps", "source_count": 1, "evidence_count": 1},
        ],
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
        "markdown": "# Evidence report\n",
    }

    ledger = build_research_evidence_ledger(
        run=run(),
        events=[
            event(
                2,
                {
                    "tool_call_id": "report",
                    "tool_name": "research.create_report",
                    "status": "completed",
                    "output": {
                        "report": report,
                        "artifact": {"id": "artifact_report"},
                    },
                },
            )
        ],
        artifacts=[],
    ).model_dump(mode="json")

    assert ledger["counts"]["weak_section_count"] == 1
    assert ledger["sections"][0]["quality_summary"] == {"high": 1, "medium": 0, "low": 0}
    assert ledger["sections"][0]["weak_quality"] is False
    assert ledger["sections"][1]["quality_summary"] == {"high": 0, "medium": 1, "low": 0}
    assert ledger["sections"][1]["weak_quality"] is True
