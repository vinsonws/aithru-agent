import asyncio
from pathlib import Path

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from aithru_agent.persistence.sqlite import SQLiteAgentEventStore, SQLiteAgentStore
from aithru_agent.settings import AgentSettings
from aithru_agent.worker.cli import main as worker_main


def test_worker_cli_processes_persisted_queued_run(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "agent.sqlite"
    settings = AgentSettings(model="test", persistence_backend="sqlite", sqlite_path=str(db_path))

    async def seed_run() -> str:
        runtime = create_agent_runtime(settings=settings)
        queued = await runtime.worker.submit_run(
            org_id="org_1",
            actor_user_id="user_1",
            task_msg="Process from CLI",
            scopes=["*"],
        )
        return queued.id

    async def read_run(run_id: str):
        store = SQLiteAgentStore(db_path)
        event_store = SQLiteAgentEventStore(db_path)
        return await store.get_run(run_id), await event_store.list_by_run(run_id)

    run_id = asyncio.run(seed_run())
    exit_code = worker_main(["--once", "--sqlite-path", str(db_path)])
    persisted, events = asyncio.run(read_run(run_id))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert persisted is not None
    assert persisted.status == AgentRunStatus.COMPLETED
    assert [event.type for event in events][-1] == "run.completed"
    assert f"processed {run_id}" in output


def test_worker_cli_loop_processes_persisted_queued_run(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "agent.sqlite"
    settings = AgentSettings(model="test", persistence_backend="sqlite", sqlite_path=str(db_path))

    async def seed_run() -> str:
        runtime = create_agent_runtime(settings=settings)
        queued = await runtime.worker.submit_run(
            org_id="org_1",
            actor_user_id="user_1",
            task_msg="Process from CLI loop",
            scopes=["*"],
        )
        return queued.id

    async def read_run(run_id: str):
        store = SQLiteAgentStore(db_path)
        event_store = SQLiteAgentEventStore(db_path)
        return await store.get_run(run_id), await event_store.list_by_run(run_id)

    run_id = asyncio.run(seed_run())
    exit_code = worker_main(
        [
            "--loop",
            "--limit",
            "1",
            "--poll-interval",
            "0.01",
            "--sqlite-path",
            str(db_path),
        ]
    )
    persisted, events = asyncio.run(read_run(run_id))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert persisted is not None
    assert persisted.status == AgentRunStatus.COMPLETED
    assert [event.type for event in events][-1] == "run.completed"
    assert "processed 1 run(s)" in output
