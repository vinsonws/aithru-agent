import subprocess
import sys
from pathlib import Path

import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.harness.drivers.scripted import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.trace import project_trace_spans


@pytest.mark.asyncio
async def test_file_report_agent_produces_report_artifact_events_and_trace() -> None:
    runtime = create_agent_runtime(
        driver=ScriptedHarnessDriver(
            [
                ScriptedStep.tool("todo.create", {"title": "Read files", "status": "running"}),
                ScriptedStep.tool(
                    "workspace.write_file",
                    {"path": "/inputs/notes.md", "content": "# Notes\nImportant input.\n"},
                ),
                ScriptedStep.tool("workspace.read_file", {"path": "/inputs/notes.md"}),
                ScriptedStep.tool(
                    "workspace.write_file",
                    {"path": "/reports/report.md", "content": "# Report\nImportant input.\n"},
                ),
                ScriptedStep.tool(
                    "artifact.create",
                    {
                        "type": "report",
                        "name": "Workspace Report",
                        "uri": "/reports/report.md",
                        "content": {"summary": "Important input."},
                    },
                ),
                ScriptedStep.message("Created /reports/report.md"),
                ScriptedStep.finish(),
            ]
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Analyze workspace files and create a report.",
        scopes=["*"],
    )
    report = await runtime.store.read_workspace_file(run.workspace_id, "/reports/report.md")
    artifacts = await runtime.store.list_artifacts(run_id=run.id)
    events = await runtime.event_store.list_by_run(run.id)
    spans = project_trace_spans(events)

    assert report.content == "# Report\nImportant input.\n"
    assert artifacts[0].type == "report"
    assert events[-1].type == "run.completed"
    assert {span.kind for span in spans} >= {"run", "model", "tool", "workspace", "artifact"}


def test_file_report_example_script_runs_successfully() -> None:
    backend_root = Path(__file__).parents[2]
    script = backend_root / "examples" / "file_report_agent.py"

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=backend_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Run status: completed" in completed.stdout
    assert "Report path: /reports/report.md" in completed.stdout
    assert "Trace span kinds:" in completed.stdout
