import asyncio

import pytest

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from aithru_agent.worker.queue import InProcessRunQueue
from tests.utils.step_runtime import Step, StepAgentRuntime


def test_in_process_queue_deduplicates_pending_run_ids() -> None:
    queue = InProcessRunQueue()

    queue.enqueue("run_1")
    queue.enqueue("run_1")

    assert queue.pop().run_id == "run_1"
    assert queue.pop() is None


@pytest.mark.asyncio
async def test_runner_join_run_waits_until_run_reaches_terminal_state() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.message("done"),
                Step.finish(),
            ]
        )
    )
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Join me",
        scopes=["*"],
    )

    join_task = asyncio.create_task(
        runtime.runner.join_run(
            queued.id,
            timeout_seconds=2,
            poll_interval_seconds=0.01,
        )
    )
    await asyncio.sleep(0.05)
    assert not join_task.done()

    await runtime.worker.drain()
    joined = await join_task

    assert joined.id == queued.id
    assert joined.status == AgentRunStatus.COMPLETED


class SlowRuntime(AgentRuntime):
    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg, deps
        await asyncio.sleep(0.2)
        return AgentRuntimeResult(content="done")


@pytest.mark.asyncio
async def test_cancelled_running_run_stays_cancelled_after_worker_returns() -> None:
    runtime = create_agent_runtime(agent_runtime=SlowRuntime())
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Cancel while active",
        scopes=["*"],
    )
    worker_task = asyncio.create_task(runtime.worker.drain())

    while True:
        run = await runtime.store.get_run(queued.id)
        if run.status == AgentRunStatus.RUNNING:
            break
        await asyncio.sleep(0.01)

    await runtime.runner.cancel_run(queued.id)
    await worker_task

    stored = await runtime.store.get_run(queued.id)
    event_types = [event.type for event in await runtime.event_store.list_by_run(queued.id)]

    assert stored.status == AgentRunStatus.CANCELLED
    assert event_types[-1] == "run.cancelled"
    assert "run.completed" not in event_types
