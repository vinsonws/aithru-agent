import subprocess
import sys
from pathlib import Path

import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.trace import project_trace_spans
from tests.utils.step_runtime import Step, StepAgentRuntime


@pytest.mark.asyncio
async def test_deep_research_skill_creates_todos_report_artifact_events_and_trace() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.message("Planning research.\n"),
                Step.tool(
                    "research.create_plan",
                    {
                        "query": "aithru deerflow parity",
                        "objective": "Check backend parity for controlled research work.",
                    },
                ),
                Step.tool(
                    "research.create_report",
                    {
                        "title": "Aithru Deep Research",
                        "query": "aithru deerflow parity",
                        "summary": "Aithru Agent can plan research and create cited report artifacts.",
                        "sources": [
                            {
                                "title": "Aithru Agent Harness",
                                "url": "https://example.com/aithru-agent",
                                "snippet": (
                                    "Aithru Agent routes real actions through controlled "
                                    "capabilities and records traceable artifacts."
                                ),
                                "source": "example",
                            }
                        ],
                    },
                ),
                Step.message("Created research report.\n"),
                Step.finish(),
            ]
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Research Aithru Agent backend parity.",
        scopes=["*"],
        skill_id="deep-research",
    )
    todos = await runtime.store.list_todos(run.id)
    artifacts = await runtime.store.list_artifacts(run_id=run.id)
    events = await runtime.event_store.list_by_run(run.id)
    spans = project_trace_spans(events)

    assert run.status.value == "completed"
    assert [todo.title for todo in todos] == [
        "Search sources",
        "Fetch and review sources",
        "Synthesize findings",
        "Create research report",
    ]
    assert len(artifacts) == 1
    assert artifacts[0].type == "report"
    assert artifacts[0].name == "Aithru Deep Research"
    assert "# Aithru Deep Research" in str(artifacts[0].content)
    assert run.result is not None
    assert run.result.artifact_ids == [artifacts[0].id]
    assert sum(event.type == "todo.created" for event in events) == 4
    assert sum(event.type == "artifact.created" for event in events) == 1
    assert events[-1].type == "run.completed"
    assert {span.kind for span in spans} >= {
        "run",
        "model",
        "message",
        "tool",
        "todo",
        "artifact",
    }


def test_deep_research_example_script_runs_successfully() -> None:
    backend_root = Path(__file__).parents[2]
    script = backend_root / "examples" / "deep_research_agent.py"

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=backend_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Run status: completed" in completed.stdout
    assert "Todos: 4" in completed.stdout
    assert "Report artifact: Aithru Deep Research" in completed.stdout
    assert "Trace span kinds:" in completed.stdout
