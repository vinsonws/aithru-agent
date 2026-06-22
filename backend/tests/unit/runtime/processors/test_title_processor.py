import pytest

from aithru_agent.domain import AgentRunStatus
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors.base import AgentRuntimeProcessorContext
from aithru_agent.runtime.processors.title import ThreadTitleProcessor
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_generates_title_from_untitled_thread_goal() -> None:
    context = await _make_context(
        goal="Compare Aithru Agent with DeerFlow for long running research tasks"
    )

    decision = await ThreadTitleProcessor().before_model(context)

    thread = await context.store.get_thread(context.run.thread_id or "")
    events = await context.event_store.list_by_run(context.run.id)
    assert decision.should_stop is False
    assert thread is not None
    assert thread.title == "Compare Aithru Agent With Deerflow For"
    assert [event.type for event in events] == ["thread.title.generated"]
    assert events[0].visibility == "debug"
    assert events[0].payload == {
        "thread_id": thread.id,
        "title": "Compare Aithru Agent With Deerflow For",
    }


@pytest.mark.asyncio
async def test_does_not_overwrite_existing_thread_title() -> None:
    context = await _make_context(
        goal="Compare Aithru Agent with DeerFlow for long running research tasks",
        thread_title="Manual Research Title",
    )

    decision = await ThreadTitleProcessor().before_model(context)

    thread = await context.store.get_thread(context.run.thread_id or "")
    assert decision.should_stop is False
    assert thread is not None
    assert thread.title == "Manual Research Title"
    assert await context.event_store.list_by_run(context.run.id) == []


@pytest.mark.asyncio
async def test_preserves_trailing_word_within_max_word_limit() -> None:
    context = await _make_context(goal="research cats and")

    decision = await ThreadTitleProcessor(max_words=3).before_model(context)

    thread = await context.store.get_thread(context.run.thread_id or "")
    assert decision.should_stop is False
    assert thread is not None
    assert thread.title == "Research Cats And"


@pytest.mark.asyncio
async def test_non_thread_run_no_ops() -> None:
    context = await _make_context(
        goal="Compare Aithru Agent with DeerFlow for long running research tasks",
        threaded=False,
    )

    decision = await ThreadTitleProcessor().before_model(context)

    assert decision.should_stop is False
    assert await context.event_store.list_by_run(context.run.id) == []


async def _make_context(
    *,
    goal: str,
    threaded: bool = True,
    thread_title: str | None = None,
) -> AgentRuntimeProcessorContext:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    thread = (
        await store.create_thread(
            org_id="org_1",
            owner_user_id="user_1",
            title=thread_title,
        )
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
        goal=goal,
        workspace_id=workspace.id,
        thread_id=thread.id if thread is not None else None,
        scopes=["agent.workspace.read"],
    )
    run = await store.update_run(queued.id, status=AgentRunStatus.RUNNING)
    return AgentRuntimeProcessorContext(
        run=run,
        store=store,
        event_writer=writer,
        event_store=event_store,
    )
