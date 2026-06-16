import asyncio

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.harness.drivers.scripted import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.trace import project_trace_spans


async def main() -> None:
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
    events = await runtime.event_store.list_by_run(run.id)
    spans = project_trace_spans(events)
    artifacts = await runtime.store.list_artifacts(run_id=run.id)

    print(f"Run id: {run.id}")
    print(f"Run status: {run.status.value}")
    print("Report path: /reports/report.md")
    print(f"Artifacts: {', '.join(artifact.name for artifact in artifacts)}")
    print(f"Events: {len(events)}")
    print(f"Trace span kinds: {', '.join(sorted({span.kind for span in spans}))}")


if __name__ == "__main__":
    asyncio.run(main())
