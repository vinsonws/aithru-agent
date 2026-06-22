import pytest

from aithru_agent.domain import AgentRunResult, AgentRunStatus
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors.base import AgentRuntimeProcessorContext
from aithru_agent.runtime.processors.memory_extraction import MemoryExtractionProcessor
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_processor_no_ops_for_non_completed_runs_without_permission_or_blank_result() -> None:
    processor = MemoryExtractionProcessor()
    contexts = [
        await _make_context(
            terminal_status=AgentRunStatus.FAILED,
            scopes=["agent.memory.write"],
            result_content="Useful completed output.",
        ),
        await _make_context(
            terminal_status=AgentRunStatus.COMPLETED,
            scopes=["agent.memory.read"],
            result_content="Useful completed output.",
        ),
        await _make_context(
            terminal_status=AgentRunStatus.COMPLETED,
            scopes=["agent.memory.write"],
            result_content=" \n\t ",
        ),
    ]

    for context in contexts:
        decision = await processor.after_terminal(context)

        assert decision.should_stop is False
        assert await context.store.list_memory_candidates(org_id=context.run.org_id) == []
        assert await context.event_store.list_by_run(context.run.id) == []


@pytest.mark.asyncio
async def test_completed_memory_write_run_creates_pending_candidate_and_audit_event() -> None:
    context = await _make_context(
        terminal_status=AgentRunStatus.COMPLETED,
        scopes=["agent.memory.write"],
        result_content="Final answer with durable user preference signal.",
        threaded=True,
    )

    decision = await MemoryExtractionProcessor().after_terminal(context)

    candidates = await context.store.list_memory_candidates(org_id=context.run.org_id)
    entries = await context.store.list_memory_entries(org_id=context.run.org_id)
    events = await context.event_store.list_by_run(context.run.id)
    assert decision.should_stop is False
    assert entries == []
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.id == f"memcand_{context.run.id}"
    assert candidate.org_id == "org_1"
    assert candidate.run_id == context.run.id
    assert candidate.scope == "thread"
    assert candidate.scope_id == context.run.thread_id
    assert candidate.key == f"run_{context.run.id}_outcome"
    assert candidate.value == "Final answer with durable user preference signal."
    assert candidate.confidence == 0.6
    assert candidate.status == "pending"
    assert candidate.resolved_at is None
    assert [event.type for event in events] == ["memory.candidate.created"]
    assert events[0].visibility == "audit"
    assert events[0].payload == {
        "candidate_id": candidate.id,
        "run_id": context.run.id,
        "scope": "thread",
        "scope_id": context.run.thread_id,
        "key": candidate.key,
        "confidence": 0.6,
        "status": "pending",
    }


@pytest.mark.asyncio
async def test_processor_truncates_value_and_is_idempotent_for_deterministic_candidate_id() -> None:
    context = await _make_context(
        terminal_status=AgentRunStatus.COMPLETED,
        scopes=["*"],
        result_content="x" * 900,
        threaded=False,
    )
    processor = MemoryExtractionProcessor()

    first = await processor.after_terminal(context)
    second = await processor.after_terminal(context)

    candidates = await context.store.list_memory_candidates(org_id=context.run.org_id)
    events = await context.event_store.list_by_run(context.run.id)
    assert first.should_stop is False
    assert second.should_stop is False
    assert len(candidates) == 1
    assert candidates[0].scope == "user"
    assert candidates[0].scope_id == context.run.actor_user_id
    assert candidates[0].value == "x" * 800
    assert [event.type for event in events] == ["memory.candidate.created"]


async def _make_context(
    *,
    terminal_status: AgentRunStatus,
    scopes: list[str],
    result_content: str | None,
    threaded: bool = False,
) -> AgentRuntimeProcessorContext:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    thread = (
        await store.create_thread(org_id="org_1", owner_user_id="user_1")
        if threaded
        else None
    )
    workspace = await store.create_workspace(
        org_id="org_1",
        thread_id=thread.id if thread else None,
    )
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Extract memory candidate",
        workspace_id=workspace.id,
        thread_id=thread.id if thread else None,
        scopes=scopes,
    )
    run = run.model_copy(
        update={
            "status": terminal_status,
            "result": AgentRunResult(content=result_content),
        }
    )
    return AgentRuntimeProcessorContext(
        run=run,
        store=store,
        event_writer=writer,
        event_store=event_store,
        terminal_status=terminal_status,
    )
