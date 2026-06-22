import pytest
from pydantic import ValidationError

from aithru_agent.domain.research import (
    ResearchLimitation,
    ResearchToolFailure,
    ResearchReportRequest,
    ResearchSource,
    build_research_report,
    research_limitation_for_blocked_todo_title,
    research_limitation_for_tool_failure,
)


def test_research_report_request_is_pydantic_validated() -> None:
    request = ResearchReportRequest(
        title="Aithru Agent research",
        query="aithru agent deerflow parity",
        summary="Aithru is closing the backend harness gap.",
        sources=[
            ResearchSource(
                title="Aithru Agent",
                url="https://example.com/aithru",
                snippet="Agent harness backend.",
                content="Detailed source content about tools, artifacts, and reports.",
                source="example",
                published_at="2026-06-18",
                section_id="evidence",
            )
        ],
    )

    assert request.title == "Aithru Agent research"
    assert request.sources[0].url == "https://example.com/aithru"
    assert request.sources[0].section_id == "evidence"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title": " ", "query": "q", "sources": []},
        {"title": "Report", "query": " ", "sources": []},
        {"title": "Report", "query": "q", "sources": [], "limitations": []},
        {
            "title": "Report",
            "query": "q",
            "sources": [{"title": "Bad", "url": "ftp://example.com"}],
        },
        {
            "title": "Report",
            "query": "q",
            "sources": [{"title": "Bad", "url": "https://example.com", "section_id": "Bad Id"}],
        },
    ],
)
def test_research_report_request_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResearchReportRequest(**kwargs)


def test_build_research_report_renders_cited_markdown() -> None:
    report = build_research_report(
        ResearchReportRequest(
            title="Aithru Agent research",
            query="aithru agent deerflow parity",
            sources=[
                ResearchSource(
                    title="Aithru Agent",
                    url="https://example.com/aithru",
                    snippet="Agent harness backend.",
                    content="Detailed source content about tools, artifacts, and reports.",
                    source="example",
                    section_id="architecture",
                ),
                ResearchSource(
                    title="DeerFlow benchmark",
                    url="https://example.com/deerflow",
                    snippet="Deep research benchmark.",
                    section_id="benchmark",
                ),
            ],
        )
    )

    assert report.title == "Aithru Agent research"
    assert report.query == "aithru agent deerflow parity"
    assert report.summary == "Collected 2 sources for `aithru agent deerflow parity`."
    assert report.findings == [
        (
            "Aithru Agent: Agent harness backend. "
            "Detailed source content about tools, artifacts, and reports."
        ),
        "DeerFlow benchmark: Deep research benchmark.",
    ]
    assert report.markdown.startswith("# Aithru Agent research\n")
    assert [summary.model_dump(mode="json") for summary in report.section_summary] == [
        {"section_id": "architecture", "source_count": 1, "evidence_count": 1},
        {"section_id": "benchmark", "source_count": 1, "evidence_count": 1},
    ]
    assert (
        "## Findings\n\n- Aithru Agent: Agent harness backend. "
        "Detailed source content about tools, artifacts, and reports. [1]"
    ) in report.markdown
    assert "## Evidence by Section\n\n- `architecture`: 1 source, 1 evidence row" in report.markdown
    assert "- `benchmark`: 1 source, 1 evidence row" in report.markdown
    assert "| # | Section | Source | Quality | Evidence |" in report.markdown
    assert "## Sources\n\n1. [Aithru Agent](https://example.com/aithru)" in report.markdown
    assert report.model_dump(mode="json")["sources"][0]["source"] == "example"


def test_build_research_report_builds_structured_evidence_rows() -> None:
    report = build_research_report(
        ResearchReportRequest(
            title="Aithru evidence research",
            query="aithru evidence",
            sources=[
                ResearchSource(
                    title="Aithru Agent",
                    url="https://example.com/aithru",
                    snippet="Search snippet.",
                    content="Fetched evidence content with additional details.",
                    source="example-search",
                    published_at="2026-06-18",
                    section_id="evidence",
                ),
                ResearchSource(
                    title="DeerFlow",
                    url="https://example.com/deerflow",
                    content="DeerFlow evidence content.",
                    section_id="benchmark",
                ),
            ],
        )
    )

    assert [row.model_dump(mode="json") for row in report.evidence] == [
        {
            "citation_number": 1,
            "title": "Aithru Agent",
            "url": "https://example.com/aithru",
            "snippet": "Search snippet.",
            "excerpt": "Fetched evidence content with additional details.",
            "source": "example-search",
            "published_at": "2026-06-18",
            "section_id": "evidence",
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
        },
        {
            "citation_number": 2,
            "title": "DeerFlow",
            "url": "https://example.com/deerflow",
            "snippet": None,
            "excerpt": "DeerFlow evidence content.",
            "source": None,
            "published_at": None,
            "section_id": "benchmark",
            "quality": {
                "label": "medium",
                "score": 70,
                "reasons": ["valid_http_source", "has_fetched_content"],
            },
        },
    ]
    assert "## Evidence" in report.markdown
    assert "| # | Section | Source | Quality | Evidence |" in report.markdown
    assert (
        "| 1 | `evidence` | [Aithru Agent](https://example.com/aithru) | high | "
        "Search snippet. Fetched evidence content with additional details. |"
    ) in report.markdown
    assert (
        "| 2 | `benchmark` | [DeerFlow](https://example.com/deerflow) | "
        "medium | DeerFlow evidence content. |"
    ) in report.markdown


def test_build_research_report_dedupes_sorts_and_labels_source_quality() -> None:
    report = build_research_report(
        ResearchReportRequest(
            title="Source quality research",
            query="aithru source quality",
            sources=[
                ResearchSource(
                    title="Low quality source",
                    url="https://example.com/low",
                ),
                ResearchSource(
                    title="Aithru Agent",
                    url="https://example.com/aithru#section",
                    snippet="Search snippet.",
                    source="search",
                ),
                ResearchSource(
                    title="Aithru Agent duplicate",
                    url="https://example.com/aithru/",
                    content="Fetched detail.",
                    published_at="2026-06-18",
                ),
            ],
        )
    )

    assert report.source_input_count == 3
    assert report.duplicate_source_count == 1
    assert report.quality_summary.model_dump(mode="json") == {
        "high": 1,
        "medium": 0,
        "low": 1,
    }
    assert [source.url for source in report.sources] == [
        "https://example.com/aithru#section",
        "https://example.com/low",
    ]
    assert [row.quality.model_dump(mode="json") for row in report.evidence] == [
        {
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
        {
            "label": "low",
            "score": 40,
            "reasons": ["valid_http_source"],
        },
    ]
    assert report.evidence[0].citation_number == 1
    assert report.evidence[0].snippet == "Search snippet."
    assert report.evidence[0].excerpt == "Fetched detail."
    assert "| 1 | [Aithru Agent](https://example.com/aithru#section) | high | Search snippet. Fetched detail. |" in report.markdown


def test_build_research_report_includes_fetched_content_with_search_snippet() -> None:
    report = build_research_report(
        ResearchReportRequest(
            title="Controlled web research",
            query="aithru controlled web",
            sources=[
                ResearchSource(
                    title="Aithru controlled source",
                    url="https://example.com/aithru",
                    snippet="Search result summary.",
                    content="Fetched page evidence with more detail.",
                ),
            ],
        )
    )

    assert report.findings == [
        "Aithru controlled source: Search result summary. Fetched page evidence with more detail."
    ]
    assert (
        "- Aithru controlled source: Search result summary. "
        "Fetched page evidence with more detail. [1]"
    ) in report.markdown


def test_build_research_report_can_create_insufficient_evidence_report() -> None:
    report = build_research_report(
        ResearchReportRequest(
            title="No source research",
            query="aithru missing sources",
            sources=[],
            limitations=[
                ResearchLimitation(
                    code="search_no_results",
                    severity="warning",
                    message="Controlled search returned no results.",
                )
            ],
        )
    )

    assert report.status == "insufficient_evidence"
    assert report.summary == "No usable sources were collected for `aithru missing sources`."
    assert report.sources == []
    assert report.evidence == []
    assert report.limitations[0].model_dump(mode="json") == {
        "code": "search_no_results",
        "severity": "warning",
        "message": "Controlled search returned no results.",
        "source_url": None,
    }
    assert "## Limitations" in report.markdown
    assert "- warning: Controlled search returned no results. (`search_no_results`)" in report.markdown


def test_build_research_report_marks_sources_with_limitations_as_partial() -> None:
    report = build_research_report(
        ResearchReportRequest(
            title="Partial research",
            query="aithru partial",
            sources=[
                ResearchSource(
                    title="Aithru Agent",
                    url="https://example.com/aithru",
                    snippet="Search snippet.",
                )
            ],
            limitations=[
                ResearchLimitation(
                    code="fetch_failed",
                    severity="error",
                    message="Fetch failed with status 500.",
                    source_url="https://example.com/aithru",
                )
            ],
        )
    )

    assert report.status == "partial"
    assert report.quality_summary.model_dump(mode="json") == {
        "high": 0,
        "medium": 1,
        "low": 0,
    }
    assert "- error: Fetch failed with status 500. (`fetch_failed`, https://example.com/aithru)" in report.markdown


def test_research_tool_failures_map_to_structured_limitations() -> None:
    search_limitation = research_limitation_for_tool_failure(
        ResearchToolFailure(
            tool_name="web.search",
            query="aithru deerflow parity",
            error_message="search provider unavailable",
        )
    )
    fetch_limitation = research_limitation_for_tool_failure(
        ResearchToolFailure(
            tool_name="web.fetch",
            url="https://example.com/aithru",
            error_message="fetch provider unavailable",
        )
    )

    assert search_limitation.model_dump(mode="json") == {
        "code": "web_search_failed",
        "severity": "warning",
        "message": (
            "Controlled web search failed for `aithru deerflow parity`: "
            "search provider unavailable."
        ),
        "source_url": None,
    }
    assert fetch_limitation.model_dump(mode="json") == {
        "code": "web_fetch_failed",
        "severity": "warning",
        "message": "Controlled web fetch failed: fetch provider unavailable.",
        "source_url": "https://example.com/aithru",
    }


def test_blocked_research_todos_map_to_report_limitations() -> None:
    assert research_limitation_for_blocked_todo_title("Search sources").model_dump(
        mode="json"
    ) == {
        "code": "research_search_blocked",
        "severity": "warning",
        "message": "Research source search was blocked before report creation.",
        "source_url": None,
    }
    assert research_limitation_for_blocked_todo_title("Fetch and review sources").model_dump(
        mode="json"
    ) == {
        "code": "research_fetch_blocked",
        "severity": "warning",
        "message": "Research source fetching was blocked before report creation.",
        "source_url": None,
    }
    assert research_limitation_for_blocked_todo_title("Custom task") is None
