import pytest

from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import ArtifactLocalTool, TodoLocalTool, WorkspaceLocalTool
from aithru_agent.domain import AgentRunStatus
from aithru_agent.harness.drivers.scripted.driver import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.trace import project_trace_spans
from aithru_agent.worker.runner import AgentWorkerRunner


def make_runner(driver: ScriptedHarnessDriver) -> tuple[AgentWorkerRunner, InMemoryAgentStore, InMemoryAgentEventStore]:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    router = AithruCapabilityRouter(
        adapters=[
            WorkspaceLocalTool(store),
            TodoLocalTool(store),
            ArtifactLocalTool(store),
        ],
        policy=ToolPolicy(require_approval_for_risk=[]),
    )
    return AgentWorkerRunner(store=store, event_writer=writer, capability_router=router, driver=driver), store, event_store


@pytest.mark.asyncio
async def test_scripted_worker_executes_tools_writes_events_and_completes_run() -> None:
    driver = ScriptedHarnessDriver(
        [
            ScriptedStep.message("I will inspect the workspace.\n"),
            ScriptedStep.tool("todo.create", {"title": "Read files", "status": "running"}),
            ScriptedStep.tool(
                "workspace.write_file",
                {"path": "/reports/report.md", "content": "# Report\nDone.\n", "media_type": "text/markdown"},
            ),
            ScriptedStep.tool(
                "artifact.create",
                {
                    "type": "report",
                    "name": "Report",
                    "uri": "/reports/report.md",
                    "content": {"path": "/reports/report.md"},
                },
            ),
            ScriptedStep.message("Report complete."),
            ScriptedStep.finish(),
        ]
    )
    runner, store, event_store = make_runner(driver)

    run = await runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write a report",
        scopes=["*"],
    )

    stored_run = await store.get_run(run.id)
    file = await store.read_workspace_file(run.workspace_id, "/reports/report.md")
    events = await event_store.list_by_run(run.id)
    event_types = [event.type for event in events]

    assert stored_run.status == AgentRunStatus.COMPLETED
    assert file.content == "# Report\nDone.\n"
    assert await store.list_artifacts(run_id=run.id)
    assert event_types == [
        "run.created",
        "run.started",
        "message.created",
        "model.started",
        "message.delta",
        "tool.proposed",
        "tool.started",
        "todo.created",
        "tool.completed",
        "tool.proposed",
        "tool.started",
        "workspace.file.created",
        "tool.completed",
        "tool.proposed",
        "tool.started",
        "artifact.created",
        "tool.completed",
        "message.delta",
        "model.completed",
        "message.completed",
        "run.completed",
    ]


@pytest.mark.asyncio
async def test_scripted_worker_emits_artifact_finalized_event_and_trace() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Finalize artifact",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    artifact = await store.create_artifact(
        org_id=run.org_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        type="report",
        name="Report",
    )
    runner = AgentWorkerRunner(
        store=store,
        event_writer=writer,
        capability_router=AithruCapabilityRouter(
            adapters=[ArtifactLocalTool(store)],
            policy=ToolPolicy(require_approval_for_risk=[]),
        ),
        driver=ScriptedHarnessDriver(
            [
                ScriptedStep.tool("artifact.finalize", {"artifact_id": artifact.id}),
                ScriptedStep.finish(),
            ]
        ),
    )

    completed = await runner.execute_run(run.id)
    events = await event_store.list_by_run(run.id)
    spans = project_trace_spans(events)
    event_types = [event.type for event in events]

    assert completed.status == AgentRunStatus.COMPLETED
    assert "artifact.finalized" in event_types
    assert next(span for span in spans if span.id == f"artifact:{artifact.id}").status == "completed"


@pytest.mark.asyncio
async def test_worker_can_cancel_a_stored_run() -> None:
    driver = ScriptedHarnessDriver([])
    runner, store, event_store = make_runner(driver)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Cancel me",
        workspace_id=workspace.id,
    )

    cancelled = await runner.cancel_run(run.id)
    events = await event_store.list_by_run(run.id)

    assert cancelled.status == AgentRunStatus.CANCELLED
    assert events[-1].type == "run.cancelled"
