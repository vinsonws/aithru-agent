from collections.abc import Callable
from pathlib import Path

import pytest

from aithru_agent.domain import AgentRunStatus
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
        goal="Status hardening",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    updated = await store.update_run(run.id, status="waiting_subagent")
    claimed = await store.claim_run(run.id)

    assert updated.status is AgentRunStatus.WAITING_SUBAGENT
    assert claimed is None

