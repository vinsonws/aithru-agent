import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from aithru_agent.harness.drivers.scripted.driver import ScriptedHarnessDriver, ScriptedStep


def report_driver() -> ScriptedHarnessDriver:
    return ScriptedHarnessDriver(
        [
            ScriptedStep.message("Writing.\n"),
            ScriptedStep.tool(
                "workspace.write_file",
                {"path": "/reports/report.md", "content": "# Report\n", "media_type": "text/markdown"},
            ),
            ScriptedStep.finish(),
        ]
    )


@pytest.mark.asyncio
async def test_worker_service_queues_run_until_work_once_executes_it() -> None:
    runtime = create_agent_runtime(driver=report_driver())

    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write a report",
        scopes=["*"],
    )
    before_events = await runtime.event_store.list_by_run(queued.id)
    before_files = await runtime.store.list_workspace_files(queued.workspace_id)

    assert queued.status == AgentRunStatus.QUEUED
    assert [event.type for event in before_events] == ["run.created"]
    assert before_files == []

    completed = await runtime.worker.work_once()
    after_events = await runtime.event_store.list_by_run(queued.id)
    after_file = await runtime.store.read_workspace_file(queued.workspace_id, "/reports/report.md")

    assert completed is not None
    assert completed.status == AgentRunStatus.COMPLETED
    assert after_file.content == "# Report\n"
    assert [event.type for event in after_events][-3:] == [
        "model.completed",
        "message.completed",
        "run.completed",
    ]
    assert await runtime.worker.work_once() is None
