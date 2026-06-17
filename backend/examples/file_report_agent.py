import asyncio

from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.settings import AgentSettings
from aithru_agent.trace import project_trace_spans


async def main() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        agent_runtime=AgentRuntime(
            model=TestModel(
                call_tools=[
                    "todo.create",
                    "workspace.write_file",
                    "workspace.read_file",
                    "artifact.create",
                ],
                custom_output_text="Created report.",
            )
        ),
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
    files = await runtime.store.list_workspace_files(run.workspace_id)
    report_path = files[0].path if files else "<none>"

    print(f"Run id: {run.id}")
    print(f"Run status: {run.status.value}")
    print(f"Report path: {report_path}")
    print(f"Artifacts: {', '.join(artifact.name for artifact in artifacts)}")
    print(f"Events: {len(events)}")
    print(f"Trace span kinds: {', '.join(sorted({span.kind for span in spans}))}")


if __name__ == "__main__":
    asyncio.run(main())
