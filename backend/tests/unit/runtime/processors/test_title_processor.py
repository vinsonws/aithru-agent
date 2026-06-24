import pytest

from aithru_agent.domain import AgentRunStatus
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors.base import AgentRuntimeProcessorContext
from aithru_agent.runtime.processors.title import TitleProvider, ThreadTitleProcessor
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_generates_title_from_first_complete_exchange() -> None:
    provider = RecordingTitleProvider(title="Aithru DeerFlow Research")
    context = await _make_context(task_msg="Compare Aithru Agent with DeerFlow")
    await context.store.append_message(
        thread_id=context.run.thread_id or "",
        role="user",
        content="Compare Aithru Agent with DeerFlow for long running research tasks",
        run_id=context.run.id,
    )
    await context.store.append_message(
        thread_id=context.run.thread_id or "",
        role="assistant",
        content="Aithru focuses on controlled harness execution while DeerFlow coordinates research.",
        run_id=context.run.id,
    )

    decision = await ThreadTitleProcessor(provider=provider).after_terminal(context)

    thread = await context.store.get_thread(context.run.thread_id or "")
    events = await context.event_store.list_by_run(context.run.id)
    assert decision.should_stop is False
    assert thread is not None
    assert thread.title == "Aithru DeerFlow Research"
    assert provider.calls == [
        {
            "user_message": "Compare Aithru Agent with DeerFlow for long running research tasks",
            "assistant_message": (
                "Aithru focuses on controlled harness execution while DeerFlow "
                "coordinates research."
            ),
            "max_words": 6,
        }
    ]
    assert [event.type for event in events] == ["thread.title.generated"]
    assert events[0].visibility == "debug"
    assert events[0].payload == {
        "thread_id": thread.id,
        "title": "Aithru DeerFlow Research",
    }


@pytest.mark.asyncio
async def test_does_not_overwrite_existing_thread_title() -> None:
    context = await _make_context(
        task_msg="Compare Aithru Agent with DeerFlow for long running research tasks",
        thread_title="Manual Research Title",
    )

    decision = await ThreadTitleProcessor().after_terminal(context)

    thread = await context.store.get_thread(context.run.thread_id or "")
    assert decision.should_stop is False
    assert thread is not None
    assert thread.title == "Manual Research Title"
    assert await context.event_store.list_by_run(context.run.id) == []


@pytest.mark.asyncio
async def test_waits_for_assistant_message_before_generating_title() -> None:
    context = await _make_context(task_msg="research cats and")
    await context.store.append_message(
        thread_id=context.run.thread_id or "",
        role="user",
        content="research cats and",
        run_id=context.run.id,
    )

    decision = await ThreadTitleProcessor(max_words=3).after_terminal(context)

    thread = await context.store.get_thread(context.run.thread_id or "")
    assert decision.should_stop is False
    assert thread is not None
    assert thread.title is None
    assert await context.event_store.list_by_run(context.run.id) == []


@pytest.mark.asyncio
async def test_falls_back_to_user_message_when_provider_returns_blank() -> None:
    context = await _make_context(task_msg="fallback title")
    await context.store.append_message(
        thread_id=context.run.thread_id or "",
        role="user",
        content="创建一个文件并写入你好世界，然后告诉我结果",
        run_id=context.run.id,
    )
    await context.store.append_message(
        thread_id=context.run.thread_id or "",
        role="assistant",
        content="文件已经创建完成。",
        run_id=context.run.id,
    )

    decision = await ThreadTitleProcessor(
        max_words=6,
        provider=RecordingTitleProvider(title="   "),
    ).after_terminal(context)

    thread = await context.store.get_thread(context.run.thread_id or "")
    assert decision.should_stop is False
    assert thread is not None
    assert thread.title == "创建一个文件并写入你好世界，然后告诉我结果"


@pytest.mark.asyncio
async def test_non_thread_run_no_ops() -> None:
    context = await _make_context(
        task_msg="Compare Aithru Agent with DeerFlow for long running research tasks",
        threaded=False,
    )

    decision = await ThreadTitleProcessor().after_terminal(context)

    assert decision.should_stop is False
    assert await context.event_store.list_by_run(context.run.id) == []


class RecordingTitleProvider(TitleProvider):
    def __init__(self, *, title: str) -> None:
        self.title = title
        self.calls: list[dict[str, object]] = []

    async def generate_title(
        self,
        *,
        run: object,
        user_message: str,
        assistant_message: str,
        max_words: int,
    ) -> str:
        del run
        self.calls.append(
            {
                "user_message": user_message,
                "assistant_message": assistant_message,
                "max_words": max_words,
            }
        )
        return self.title


async def _make_context(
    *,
    task_msg: str,
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
        task_msg=task_msg,
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
        terminal_status=AgentRunStatus.COMPLETED,
    )
