import asyncio
from datetime import timedelta

import pytest

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunRetryPolicy, AgentRunStatus
from aithru_agent.domain.errors import AgentError
from aithru_agent.worker import AgentWorkerHeartbeatPolicy, AgentWorkerLoopPolicy
from tests.utils.step_runtime import Step, StepAgentRuntime


def one_second_before(timestamp: str) -> str:
    from datetime import datetime

    value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return (value - timedelta(seconds=1)).isoformat(timespec="seconds").replace("+00:00", "Z")


def report_driver() -> StepAgentRuntime:
    return StepAgentRuntime(
        [
            Step.message("Writing.\n"),
            Step.tool(
                "workspace.write_file",
                {"path": "/reports/report.md", "content": "# Report\n", "media_type": "text/markdown"},
            ),
            Step.finish(),
        ]
    )


class SlowRuntime(AgentRuntime):
    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg, deps
        await asyncio.sleep(0.1)
        return AgentRuntimeResult(content="done")


class FailsOnceRuntime(AgentRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg, deps
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary model outage")
        return AgentRuntimeResult(content="recovered")


class AlwaysFailsRuntime(AgentRuntime):
    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg, deps
        raise RuntimeError("still unavailable")


class AgentErrorRuntime(AgentRuntime):
    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg, deps
        raise AgentError("TOOL_DENIED", "Tool denied")


def test_worker_heartbeat_policy_derives_bounded_interval_from_lease() -> None:
    policy = AgentWorkerHeartbeatPolicy()

    assert policy.interval_for_lease(3) == 1.0
    assert policy.interval_for_lease(90) == 30.0
    assert policy.interval_for_lease(600) == 60.0


def test_worker_loop_policy_accepts_poll_and_idle_timeout_intervals() -> None:
    policy = AgentWorkerLoopPolicy(poll_interval_seconds=0.05, idle_timeout_seconds=1.5)

    assert policy.poll_interval_seconds == 0.05
    assert policy.idle_timeout_seconds == 1.5


@pytest.mark.asyncio
async def test_worker_service_queues_run_until_work_once_executes_it() -> None:
    runtime = create_agent_runtime(agent_runtime=report_driver())

    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Write a report",
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
    assert [event.type for event in after_events][-4:] == [
        "model.completed",
        "message.completed",
        "memory.candidate.created",
        "run.completed",
    ]
    assert await runtime.worker.work_once() is None


@pytest.mark.asyncio
async def test_worker_service_schedules_retry_then_completes_after_backoff() -> None:
    driver = FailsOnceRuntime()
    runtime = create_agent_runtime(agent_runtime=driver)
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Retry once",
        scopes=["*"],
        retry_policy=AgentRunRetryPolicy(
            max_attempts=2,
            initial_delay_seconds=30,
            backoff_multiplier=2,
        ),
    )

    retried = await runtime.worker.work_once()
    assert retried.retry_state is not None
    early = await runtime.runner.claim_next_queued_run(
        worker_id="worker_test",
        claimed_at=one_second_before(retried.retry_state.next_retry_at),
    )
    ready = await runtime.runner.claim_next_queued_run(
        worker_id="worker_test",
        claimed_at=retried.retry_state.next_retry_at,
    )
    completed = await runtime.runner.execute_claimed_run(ready.id)
    events = await runtime.event_store.list_by_run(queued.id)
    event_types = [event.type for event in events]
    retry_event = next(event for event in events if event.type == "run.retry.scheduled")

    assert retried.status == AgentRunStatus.QUEUED
    assert retried.retry_state.attempt == 1
    assert early is None
    assert ready is not None
    assert completed.status == AgentRunStatus.COMPLETED
    assert driver.calls == 2
    assert retry_event.payload["attempt"] == 1
    assert retry_event.payload["max_attempts"] == 2
    assert retry_event.payload["next_retry_at"] == retried.retry_state.next_retry_at
    assert event_types[-1] == "run.completed"
    assert "run.failed" not in event_types


@pytest.mark.asyncio
async def test_worker_service_loop_picks_up_delayed_retry_when_backoff_expires() -> None:
    driver = FailsOnceRuntime()
    runtime = create_agent_runtime(agent_runtime=driver)
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Retry after loop waits",
        scopes=["*"],
        retry_policy=AgentRunRetryPolicy(max_attempts=2, initial_delay_seconds=1),
    )

    processed = await runtime.worker.run_loop(
        policy=AgentWorkerLoopPolicy(poll_interval_seconds=0.05),
        limit=2,
    )
    events = await runtime.event_store.list_by_run(queued.id)
    event_types = [event.type for event in events]

    assert [run.status for run in processed] == [
        AgentRunStatus.QUEUED,
        AgentRunStatus.COMPLETED,
    ]
    assert driver.calls == 2
    assert "run.retry.scheduled" in event_types
    assert event_types[-1] == "run.completed"


@pytest.mark.asyncio
async def test_worker_service_loop_exits_after_idle_timeout() -> None:
    runtime = create_agent_runtime(agent_runtime=report_driver())

    processed = await runtime.worker.run_loop(
        policy=AgentWorkerLoopPolicy(
            poll_interval_seconds=0.01,
            idle_timeout_seconds=0.02,
        )
    )

    assert processed == []


@pytest.mark.asyncio
async def test_worker_service_loop_exits_when_stop_event_is_set() -> None:
    runtime = create_agent_runtime(agent_runtime=report_driver())
    stop_event = asyncio.Event()
    stop_event.set()

    processed = await runtime.worker.run_loop(
        policy=AgentWorkerLoopPolicy(poll_interval_seconds=0.01),
        stop_event=stop_event,
    )

    assert processed == []


@pytest.mark.asyncio
async def test_worker_service_does_not_retry_agent_error_failures() -> None:
    runtime = create_agent_runtime(agent_runtime=AgentErrorRuntime())
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Do not retry policy failures",
        scopes=["*"],
        retry_policy=AgentRunRetryPolicy(max_attempts=3, initial_delay_seconds=1),
    )

    failed = await runtime.worker.work_once()
    events = await runtime.event_store.list_by_run(queued.id)
    event_types = [event.type for event in events]

    assert failed.status == AgentRunStatus.FAILED
    assert event_types[-2:] == ["model.failed", "run.failed"]
    assert "run.retry.scheduled" not in event_types


@pytest.mark.asyncio
async def test_worker_service_emits_retry_exhausted_before_terminal_failure() -> None:
    runtime = create_agent_runtime(agent_runtime=AlwaysFailsRuntime())
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Exhaust retries",
        scopes=["*"],
        retry_policy=AgentRunRetryPolicy(max_attempts=2, initial_delay_seconds=0),
    )

    scheduled = await runtime.worker.work_once()
    failed = await runtime.worker.work_once()
    events = await runtime.event_store.list_by_run(queued.id)
    event_types = [event.type for event in events]
    exhausted = next(event for event in events if event.type == "run.retry.exhausted")

    assert scheduled.status == AgentRunStatus.QUEUED
    assert failed.status == AgentRunStatus.FAILED
    assert exhausted.payload["attempt"] == 2
    assert exhausted.payload["max_attempts"] == 2
    assert exhausted.payload["error"]["message"] == "still unavailable"
    assert event_types[-3:] == ["run.retry.exhausted", "model.failed", "run.failed"]


@pytest.mark.asyncio
async def test_worker_service_claim_uses_worker_identity() -> None:
    runtime = create_agent_runtime(agent_runtime=SlowRuntime())
    runtime.worker.worker_id = "worker_test"
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Track worker identity",
        scopes=["*"],
    )

    worker_task = asyncio.create_task(runtime.worker.work_once())
    while True:
        running = await runtime.store.get_run(queued.id)
        if running.status == AgentRunStatus.RUNNING and running.claim is not None:
            break
        await asyncio.sleep(0.01)

    await worker_task

    assert running.claim.worker_id == "worker_test"
    assert running.claim.attempt == 1


@pytest.mark.asyncio
async def test_worker_service_can_renew_active_claim_with_worker_identity() -> None:
    runtime = create_agent_runtime(agent_runtime=SlowRuntime())
    runtime.worker.worker_id = "worker_test"
    runtime.worker.lease_seconds = 60
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Renew active claim",
        scopes=["*"],
    )
    claimed = await runtime.store.claim_run(
        queued.id,
        worker_id="worker_test",
        lease_seconds=300,
    )

    renewed = await runtime.worker.renew_claim(queued.id)

    assert claimed is not None
    assert renewed is not None
    assert renewed.claim is not None
    assert renewed.claim.worker_id == "worker_test"
    assert renewed.claim.attempt == 1
    assert renewed.claim.last_heartbeat_at is not None
    assert renewed.claim.lease_expires_at > renewed.claim.last_heartbeat_at


@pytest.mark.asyncio
async def test_worker_service_auto_renews_active_claim_while_run_executes() -> None:
    runtime = create_agent_runtime(agent_runtime=SlowRuntime())
    runtime.worker.worker_id = "worker_test"
    runtime.worker.lease_seconds = 60
    runtime.worker.heartbeat_policy = AgentWorkerHeartbeatPolicy(
        interval_seconds=0.01,
        min_interval_seconds=0.01,
        max_interval_seconds=1.0,
    )
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Renew while running",
        scopes=["*"],
    )

    worker_task = asyncio.create_task(runtime.worker.work_once())
    heartbeat_claim = None
    for _ in range(50):
        running = await runtime.store.get_run(queued.id)
        if (
            running.status == AgentRunStatus.RUNNING
            and running.claim is not None
            and running.claim.last_heartbeat_at is not None
        ):
            heartbeat_claim = running.claim
            break
        await asyncio.sleep(0.01)
    completed = await worker_task

    assert heartbeat_claim is not None
    assert heartbeat_claim.worker_id == "worker_test"
    assert heartbeat_claim.attempt == 1
    assert completed.status == AgentRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_worker_service_heartbeat_renew_failure_does_not_fail_run() -> None:
    runtime = create_agent_runtime(agent_runtime=SlowRuntime())
    runtime.worker.heartbeat_policy = AgentWorkerHeartbeatPolicy(
        interval_seconds=0.01,
        min_interval_seconds=0.01,
        max_interval_seconds=1.0,
    )
    renewal_attempts = 0

    async def failing_renew_claim(run_id: str):
        nonlocal renewal_attempts
        del run_id
        renewal_attempts += 1
        raise RuntimeError("heartbeat store unavailable")

    runtime.worker.renew_claim = failing_renew_claim
    await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Keep running when heartbeat fails",
        scopes=["*"],
    )

    completed = await runtime.worker.work_once()

    assert renewal_attempts > 0
    assert completed.status == AgentRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_worker_service_emits_audit_event_when_reclaiming_stale_claim() -> None:
    runtime = create_agent_runtime(agent_runtime=report_driver())
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Reclaim stale work",
        scopes=["*"],
    )
    claimed = await runtime.store.claim_run(
        queued.id,
        worker_id="worker_old",
        claimed_at="2026-06-18T00:00:00Z",
        lease_seconds=1,
    )
    runtime.worker.worker_id = "worker_new"

    completed = await runtime.worker.work_once()
    events = await runtime.event_store.list_by_run(queued.id)
    reclaim_event = next(event for event in events if event.type == "run.claim.reclaimed")

    assert claimed is not None
    assert completed is not None
    assert reclaim_event.visibility == "audit"
    assert reclaim_event.payload == {
        "previous_worker_id": "worker_old",
        "worker_id": "worker_new",
        "attempt": 2,
        "previous_lease_expires_at": "2026-06-18T00:00:01Z",
    }


@pytest.mark.asyncio
async def test_worker_service_rejects_run_thread_from_another_org() -> None:
    runtime = create_agent_runtime(agent_runtime=report_driver())
    thread = await runtime.store.create_thread(
        org_id="org_2",
        owner_user_id="user_1",
        title="Other org",
    )

    with pytest.raises(AgentError) as exc:
        await runtime.worker.submit_run(
            org_id="org_1",
            actor_user_id="user_1",
            task_msg="Attach to another org thread",
            scopes=["*"],
            thread_id=thread.id,
        )

    runs = await runtime.store.list_runs()

    assert exc.value.code == "NOT_FOUND"
    assert exc.value.message == f"Thread not found: {thread.id}"
    assert runs == []


@pytest.mark.asyncio
async def test_worker_service_rejects_run_thread_owned_by_another_user() -> None:
    runtime = create_agent_runtime(agent_runtime=report_driver())
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_2",
        title="Other user",
    )

    with pytest.raises(AgentError) as exc:
        await runtime.worker.submit_run(
            org_id="org_1",
            actor_user_id="user_1",
            task_msg="Attach to another user's thread",
            scopes=["*"],
            thread_id=thread.id,
        )

    runs = await runtime.store.list_runs()

    assert exc.value.code == "NOT_FOUND"
    assert exc.value.message == f"Thread not found: {thread.id}"
    assert runs == []
