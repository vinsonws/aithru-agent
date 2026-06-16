from pathlib import Path

import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from aithru_agent.harness.drivers.scripted.driver import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.persistence.sqlite import SQLiteAgentEventStore, SQLiteAgentStore
from aithru_agent.stream import AgentEventWriter


@pytest.mark.asyncio
async def test_sqlite_store_persists_runs_workspace_files_and_events(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    event_store = SQLiteAgentEventStore(db_path)
    writer = AgentEventWriter(event_store)

    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Persist this",
        workspace_id=workspace.id,
        scopes=["agent.workspace.write"],
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/report.md",
        content="# Report\n",
        media_type="text/markdown",
    )
    completed = await store.update_run(run.id, status=AgentRunStatus.COMPLETED)
    await writer.write(
        run_id=run.id,
        type="run.completed",
        source={"kind": "harness"},
        payload={"status": "completed"},
    )

    reopened_store = SQLiteAgentStore(db_path)
    reopened_events = SQLiteAgentEventStore(db_path)
    persisted_run = await reopened_store.get_run(run.id)
    persisted_file = await reopened_store.read_workspace_file(workspace.id, "/reports/report.md")
    events = await reopened_events.list_by_run(run.id)

    assert completed.status == AgentRunStatus.COMPLETED
    assert persisted_run is not None
    assert persisted_run.status == AgentRunStatus.COMPLETED
    assert persisted_run.scopes == ["agent.workspace.write"]
    assert persisted_file.content == "# Report\n"
    assert [event.type for event in events] == ["run.completed"]


@pytest.mark.asyncio
async def test_runtime_can_execute_worker_runs_on_sqlite_store(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    runtime = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        driver=ScriptedHarnessDriver(
            [
                ScriptedStep.tool(
                    "workspace.write_file",
                    {"path": "/reports/report.md", "content": "# Report\n"},
                ),
                ScriptedStep.finish(),
            ]
        ),
    )

    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write report",
        scopes=["*"],
    )
    await runtime.worker.drain()

    reopened_store = SQLiteAgentStore(db_path)
    reopened_events = SQLiteAgentEventStore(db_path)
    persisted_run = await reopened_store.get_run(queued.id)
    persisted_file = await reopened_store.read_workspace_file(queued.workspace_id, "/reports/report.md")
    events = await reopened_events.list_by_run(queued.id)

    assert persisted_run is not None
    assert persisted_run.status == AgentRunStatus.COMPLETED
    assert persisted_file.content == "# Report\n"
    assert [event.type for event in events][-1] == "run.completed"


@pytest.mark.asyncio
async def test_worker_discovers_queued_sqlite_runs_across_runtime_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    api_runtime = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        driver=ScriptedHarnessDriver([]),
    )
    queued = await api_runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Execute elsewhere",
        scopes=["*"],
    )

    worker_runtime = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        driver=ScriptedHarnessDriver([ScriptedStep.finish()]),
    )
    completed = await worker_runtime.worker.work_once()

    assert completed is not None
    assert completed.id == queued.id
    assert completed.status == AgentRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_sqlite_workers_claim_queued_runs_once_across_runtime_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    api_runtime = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        driver=ScriptedHarnessDriver([]),
    )
    queued = await api_runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Claim once",
        scopes=["*"],
    )
    worker_one = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        driver=ScriptedHarnessDriver([ScriptedStep.finish()]),
    )
    worker_two = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        driver=ScriptedHarnessDriver([ScriptedStep.finish()]),
    )

    claimed_one = await worker_one.runner.claim_next_queued_run()
    claimed_two = await worker_two.runner.claim_next_queued_run()

    assert claimed_one is not None
    assert claimed_one.id == queued.id
    assert claimed_one.status == AgentRunStatus.RUNNING
    assert claimed_two is None
