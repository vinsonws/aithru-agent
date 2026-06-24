import pytest

from aithru_agent.domain import AgentRunStatus
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors.base import AgentRuntimeProcessorContext
from aithru_agent.runtime.processors.clarification import ClarificationPreflightProcessor
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_short_threaded_goal_with_input_scope_pauses_and_emits_events() -> None:
    context = await _make_context(task_msg="", scopes=["agent.input.write"])

    decision = await ClarificationPreflightProcessor().before_model(context)

    events = await context.event_store.list_by_run(context.run.id)
    assert decision.paused_run is not None
    assert decision.paused_run.status == AgentRunStatus.WAITING_INPUT
    assert [event.type for event in events] == ["input.requested", "run.paused"]
    assert events[0].payload == {
        "input_request_id": f"empty_task_msg_{context.run.id}",
        "tool_call_id": f"empty_task_msg_{context.run.id}",
        "prompt": "What should the agent help you with?",
        "reason": "The run task message is empty.",
    }
    assert events[1].payload == {
        "status": "waiting_input",
        **events[0].payload,
    }


@pytest.mark.asyncio
async def test_short_threaded_goal_without_input_scope_no_ops() -> None:
    context = await _make_context(task_msg="Fix it", scopes=["agent.workspace.read"])

    decision = await ClarificationPreflightProcessor().before_model(context)

    stored = await context.store.get_run(context.run.id)
    assert decision.should_stop is False
    assert stored is not None
    assert stored.status == AgentRunStatus.RUNNING
    assert await context.event_store.list_by_run(context.run.id) == []


@pytest.mark.asyncio
async def test_non_thread_run_no_ops() -> None:
    context = await _make_context(
        task_msg="Fix it",
        scopes=["agent.input.write"],
        threaded=False,
    )

    decision = await ClarificationPreflightProcessor().before_model(context)

    stored = await context.store.get_run(context.run.id)
    assert decision.should_stop is False
    assert stored is not None
    assert stored.status == AgentRunStatus.RUNNING
    assert await context.event_store.list_by_run(context.run.id) == []


@pytest.mark.asyncio
async def test_long_enough_goal_no_ops() -> None:
    context = await _make_context(
        task_msg="Fix the reporting bug",
        scopes=["agent.input.write"],
    )

    decision = await ClarificationPreflightProcessor().before_model(context)

    stored = await context.store.get_run(context.run.id)
    assert decision.should_stop is False
    assert stored is not None
    assert stored.status == AgentRunStatus.RUNNING
    assert await context.event_store.list_by_run(context.run.id) == []


async def _make_context(
    *,
    task_msg: str,
    scopes: list[str],
    threaded: bool = True,
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
        thread_id=thread.id if thread is not None else None,
    )
    queued = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg=task_msg,
        workspace_id=workspace.id,
        thread_id=thread.id if thread is not None else None,
        scopes=scopes,
    )
    run = await store.update_run(queued.id, status=AgentRunStatus.RUNNING)
    return AgentRuntimeProcessorContext(
        run=run,
        store=store,
        event_writer=writer,
        event_store=event_store,
    )
