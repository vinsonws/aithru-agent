from aithru_agent.domain import AgentRun
from aithru_agent.memory import (
    LongTermMemoryMessage,
    NoopLongTermMemoryProvider,
    can_read_long_term_memory,
    can_write_long_term_memory,
    identity_for_run,
)


def run_fixture() -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Remember my preference.",
        workspace_id="workspace_1",
        thread_id="thread_1",
        skill_id="research",
        scopes=["agent.memory.read", "agent.memory.write"],
        status="queued",
        started_at="2026-06-25T00:00:00Z",
    )


def test_memory_scope_helpers_require_memory_scopes() -> None:
    assert can_read_long_term_memory(["agent.memory.read"]) is True
    assert can_read_long_term_memory(["*"]) is True
    assert can_read_long_term_memory(["agent.workspace.read"]) is False
    assert can_write_long_term_memory(["agent.memory.write"]) is True
    assert can_write_long_term_memory(["*"]) is True
    assert can_write_long_term_memory(["agent.memory.read"]) is False


def test_identity_for_run_is_tenant_safe() -> None:
    identity = identity_for_run(
        run_fixture(),
        app_id="prod:aithru-agent",
        default_agent_id="aithru-agent",
    )

    assert identity.user_id == "org_1:user_1"
    assert identity.app_id == "prod:aithru-agent"
    assert identity.agent_id == "research"
    assert identity.run_id == "run_1"
    assert identity.metadata["org_id"] == "org_1"
    assert identity.metadata["actor_user_id"] == "user_1"
    assert identity.metadata["thread_id"] == "thread_1"
    assert identity.metadata["workspace_id"] == "workspace_1"
    assert identity.metadata["skill_id"] == "research"


async def test_noop_provider_returns_empty_results() -> None:
    provider = NoopLongTermMemoryProvider()

    assert await provider.search(run=run_fixture(), query="preference", limit=5) == []
    result = await provider.add_messages(
        run=run_fixture(),
        messages=[LongTermMemoryMessage(role="user", content="Remember this.")],
    )

    assert result.status == "skipped"
    assert result.event_id is None
    delete = await provider.delete_memory(memory_id="mem_1")
    assert delete.deleted is False
