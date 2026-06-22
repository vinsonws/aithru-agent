import pytest
from pydantic import ValidationError

from aithru_agent.domain.research import (
    ResearchPlanRequest,
    ResearchPlanSection,
    ResearchPlanStep,
    build_research_plan,
    research_todo_progress_for_tool,
)


def test_research_plan_request_builds_default_runtime_steps() -> None:
    plan = build_research_plan(
        ResearchPlanRequest(
            query="aithru deerflow parity",
            objective="Compare backend completeness.",
        )
    )

    assert plan.query == "aithru deerflow parity"
    assert plan.objective == "Compare backend completeness."
    assert [step.phase for step in plan.steps] == ["search", "fetch", "synthesize", "report"]
    assert [step.title for step in plan.steps] == [
        "Search sources",
        "Fetch and review sources",
        "Synthesize findings",
        "Create research report",
    ]
    assert plan.steps[0].description == "Find relevant sources for `aithru deerflow parity`."
    assert [section.model_dump(mode="json") for section in plan.sections] == [
        {
            "section_id": "background",
            "title": "Background and context",
            "question": "What background and current context matter for `aithru deerflow parity`?",
            "priority": "medium",
        },
        {
            "section_id": "evidence",
            "title": "Direct evidence",
            "question": "What evidence directly answers `aithru deerflow parity`?",
            "priority": "high",
        },
        {
            "section_id": "gaps",
            "title": "Gaps and limitations",
            "question": "What gaps, risks, or limitations remain for `aithru deerflow parity`?",
            "priority": "medium",
        },
    ]


def test_research_plan_request_accepts_custom_steps() -> None:
    plan = build_research_plan(
        ResearchPlanRequest(
            query="aithru",
            sections=[
                ResearchPlanSection(
                    section_id="architecture",
                    title="Architecture",
                    question="How is the backend structured?",
                    priority="high",
                )
            ],
            steps=[
                ResearchPlanStep(
                    phase="search",
                    title="Search official docs",
                    description="Use controlled search.",
                ),
                ResearchPlanStep(
                    phase="report",
                    title="Write summary",
                ),
            ],
        )
    )

    assert [step.title for step in plan.steps] == ["Search official docs", "Write summary"]
    assert plan.steps[1].description is None
    assert [section.model_dump(mode="json") for section in plan.sections] == [
        {
            "section_id": "architecture",
            "title": "Architecture",
            "question": "How is the backend structured?",
            "priority": "high",
        }
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": " "},
        {"query": "aithru", "objective": " "},
        {"query": "aithru", "steps": []},
        {"query": "aithru", "steps": [{"phase": "workflow", "title": "Bad"}]},
        {"query": "aithru", "steps": [{"phase": "search", "title": " "}]},
        {"query": "aithru", "sections": []},
        {
            "query": "aithru",
            "sections": [{"section_id": "Bad Id", "title": "Bad", "question": "Why?"}],
        },
        {
            "query": "aithru",
            "sections": [{"section_id": "valid", "title": " ", "question": "Why?"}],
        },
        {
            "query": "aithru",
            "sections": [{"section_id": "valid", "title": "Good", "question": " "}],
        },
    ],
)
def test_research_plan_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResearchPlanRequest(**kwargs)


def test_research_todo_progress_maps_completed_tools_to_runtime_todos() -> None:
    assert [
        progress.model_dump(mode="json")
        for progress in research_todo_progress_for_tool("web.search")
    ] == [
        {
            "tool_name": "web.search",
            "todo_title": "Search sources",
            "status": "done",
        }
    ]
    assert [
        progress.model_dump(mode="json")
        for progress in research_todo_progress_for_tool("web.fetch")
    ] == [
        {
            "tool_name": "web.fetch",
            "todo_title": "Fetch and review sources",
            "status": "done",
        }
    ]
    assert [
        progress.model_dump(mode="json")
        for progress in research_todo_progress_for_tool("research.create_report")
    ] == [
        {
            "tool_name": "research.create_report",
            "todo_title": "Synthesize findings",
            "status": "done",
        },
        {
            "tool_name": "research.create_report",
            "todo_title": "Create research report",
            "status": "done",
        },
    ]
    assert research_todo_progress_for_tool("workspace.read_file") == []


def test_research_todo_progress_maps_failed_web_tools_to_blocked_runtime_todos() -> None:
    assert [
        progress.model_dump(mode="json")
        for progress in research_todo_progress_for_tool("web.search", outcome="failed")
    ] == [
        {
            "tool_name": "web.search",
            "todo_title": "Search sources",
            "status": "blocked",
        }
    ]
    assert [
        progress.model_dump(mode="json")
        for progress in research_todo_progress_for_tool("web.fetch", outcome="failed")
    ] == [
        {
            "tool_name": "web.fetch",
            "todo_title": "Fetch and review sources",
            "status": "blocked",
        }
    ]
