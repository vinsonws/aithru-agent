from collections.abc import Callable
from pathlib import Path

import pytest

from aithru_agent.domain import AgentRunRetryPolicy, AgentRunRetryState, AgentRunStatus
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.persistence.sqlite import SQLiteAgentStore


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_update_run_validates_string_status_into_domain_enum(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Status hardening",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    running = await store.claim_run(run.id)
    assert running is not None
    updated = await store.update_run(running.id, status="waiting_subagent")
    claimed = await store.claim_run(run.id)

    assert updated.status is AgentRunStatus.WAITING_SUBAGENT
    assert claimed is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_claim_run_records_persistent_worker_lease(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Claim with lease",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    claimed = await store.claim_run(
        run.id,
        worker_id="worker_a",
        claimed_at="2026-06-18T00:00:00Z",
        lease_seconds=30,
    )
    second_claim = await store.claim_run(
        run.id,
        worker_id="worker_b",
        claimed_at="2026-06-18T00:00:10Z",
        lease_seconds=30,
    )
    stored = await store.get_run(run.id)

    assert claimed is not None
    assert claimed.status is AgentRunStatus.RUNNING
    assert claimed.claim is not None
    assert claimed.claim.worker_id == "worker_a"
    assert claimed.claim.claimed_at == "2026-06-18T00:00:00Z"
    assert claimed.claim.lease_expires_at == "2026-06-18T00:00:30Z"
    assert claimed.claim.attempt == 1
    assert second_claim is None
    assert stored.claim == claimed.claim


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_expired_running_claim_can_be_reclaimed(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Reclaim stale lease",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    first_claim = await store.claim_run(
        run.id,
        worker_id="worker_a",
        claimed_at="2026-06-18T00:00:00Z",
        lease_seconds=30,
    )
    reclaimed = await store.claim_run(
        run.id,
        worker_id="worker_b",
        claimed_at="2026-06-18T00:00:31Z",
        lease_seconds=60,
    )

    assert first_claim is not None
    assert reclaimed is not None
    assert reclaimed.status is AgentRunStatus.RUNNING
    assert reclaimed.claim is not None
    assert reclaimed.claim.worker_id == "worker_b"
    assert reclaimed.claim.claimed_at == "2026-06-18T00:00:31Z"
    assert reclaimed.claim.lease_expires_at == "2026-06-18T00:01:31Z"
    assert reclaimed.claim.attempt == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_claim_next_picks_expired_running_claim_when_no_queued_run_exists(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Reclaim next stale lease",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    first_claim = await store.claim_run(
        run.id,
        worker_id="worker_a",
        claimed_at="2026-06-18T00:00:00Z",
        lease_seconds=30,
    )
    reclaimed = await store.claim_next_queued_run(
        worker_id="worker_b",
        claimed_at="2026-06-18T00:00:31Z",
        lease_seconds=30,
    )

    assert first_claim is not None
    assert reclaimed is not None
    assert reclaimed.id == run.id
    assert reclaimed.claim is not None
    assert reclaimed.claim.worker_id == "worker_b"
    assert reclaimed.claim.attempt == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_queued_retry_run_is_not_claimed_until_backoff_time(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Backoff retry",
        workspace_id=workspace.id,
        scopes=["*"],
        retry_policy=AgentRunRetryPolicy(max_attempts=2, initial_delay_seconds=30),
    )
    await store.update_run(
        run.id,
        retry_state=AgentRunRetryState(
            attempt=1,
            next_retry_at="2026-06-18T00:00:30Z",
            last_error={"message": "temporary"},
        ),
    )

    early = await store.claim_next_queued_run(
        worker_id="worker_a",
        claimed_at="2026-06-18T00:00:29Z",
    )
    ready = await store.claim_next_queued_run(
        worker_id="worker_a",
        claimed_at="2026-06-18T00:00:30Z",
    )

    assert early is None
    assert ready is not None
    assert ready.id == run.id
    assert ready.status is AgentRunStatus.RUNNING


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_run_claim_can_be_renewed_by_owning_worker(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Renew lease",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    claimed = await store.claim_run(
        run.id,
        worker_id="worker_a",
        claimed_at="2026-06-18T00:00:00Z",
        lease_seconds=30,
    )

    renewed = await store.renew_run_claim(
        run.id,
        worker_id="worker_a",
        heartbeat_at="2026-06-18T00:00:20Z",
        lease_seconds=45,
    )

    assert claimed is not None
    assert renewed is not None
    assert renewed.claim is not None
    assert renewed.claim.worker_id == "worker_a"
    assert renewed.claim.claimed_at == "2026-06-18T00:00:00Z"
    assert renewed.claim.last_heartbeat_at == "2026-06-18T00:00:20Z"
    assert renewed.claim.lease_expires_at == "2026-06-18T00:01:05Z"
    assert renewed.claim.attempt == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_run_claim_renewal_rejects_non_owner_or_expired_claim(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Reject bad renew",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    claimed = await store.claim_run(
        run.id,
        worker_id="worker_a",
        claimed_at="2026-06-18T00:00:00Z",
        lease_seconds=30,
    )

    wrong_worker = await store.renew_run_claim(
        run.id,
        worker_id="worker_b",
        heartbeat_at="2026-06-18T00:00:10Z",
        lease_seconds=30,
    )
    expired = await store.renew_run_claim(
        run.id,
        worker_id="worker_a",
        heartbeat_at="2026-06-18T00:00:31Z",
        lease_seconds=30,
    )
    stored = await store.get_run(run.id)

    assert claimed is not None
    assert wrong_worker is None
    assert expired is None
    assert stored.claim == claimed.claim


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_active_run_claim_is_cleared_when_run_pauses_or_completes(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Clear lease",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    running = await store.claim_run(
        run.id,
        worker_id="worker_a",
        claimed_at="2026-06-18T00:00:00Z",
        lease_seconds=30,
    )
    assert running is not None

    waiting = await store.update_run(running.id, status=AgentRunStatus.WAITING_INPUT)
    queued = await store.update_run(waiting.id, status=AgentRunStatus.QUEUED)
    running_again = await store.claim_run(
        queued.id,
        worker_id="worker_b",
        claimed_at="2026-06-18T00:00:05Z",
        lease_seconds=30,
    )
    completed = await store.update_run(queued.id, status=AgentRunStatus.COMPLETED)

    assert waiting.claim is None
    assert queued.claim is None
    assert running_again is not None
    assert running_again.claim is not None
    assert completed.claim is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_terminal_run_status_cannot_be_overwritten(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Protect terminal status",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    running = await store.claim_run(run.id)
    assert running is not None
    await store.update_run(running.id, status=AgentRunStatus.COMPLETED)

    with pytest.raises(AgentError, match="terminal"):
        await store.update_run(running.id, status=AgentRunStatus.RUNNING)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_queued_run_cannot_jump_directly_to_waiting_approval(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Invalid direct wait",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    with pytest.raises(AgentError, match="Invalid run status transition"):
        await store.update_run(run.id, status=AgentRunStatus.WAITING_APPROVAL)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_running_run_can_pause_resume_and_complete(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Pause and resume",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    running = await store.claim_run(run.id)
    assert running is not None
    waiting = await store.update_run(running.id, status=AgentRunStatus.WAITING_APPROVAL)
    resumed = await store.update_run(waiting.id, status=AgentRunStatus.RUNNING)
    completed = await store.update_run(resumed.id, status=AgentRunStatus.COMPLETED)

    assert completed.status is AgentRunStatus.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_factory",
    [
        lambda tmp_path: InMemoryAgentStore(),
        lambda tmp_path: SQLiteAgentStore(tmp_path / "agent.sqlite"),
    ],
)
async def test_waiting_input_run_can_resume_through_queue(
    tmp_path: Path,
    store_factory: Callable[[Path], object],
) -> None:
    store = store_factory(tmp_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Pause for input",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    running = await store.claim_run(run.id)
    assert running is not None
    waiting = await store.update_run(running.id, status=AgentRunStatus.WAITING_INPUT)
    queued = await store.update_run(waiting.id, status=AgentRunStatus.QUEUED)
    claimed = await store.claim_run(queued.id)

    assert waiting.status is AgentRunStatus.WAITING_INPUT
    assert queued.status is AgentRunStatus.QUEUED
    assert claimed is not None
    assert claimed.status is AgentRunStatus.RUNNING
