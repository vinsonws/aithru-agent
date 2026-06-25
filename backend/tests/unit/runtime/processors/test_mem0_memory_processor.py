from aithru_agent.domain import AgentRunStatus
from aithru_agent.memory import LongTermMemoryAddResult
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors.base import AgentRuntimeProcessorContext
from aithru_agent.runtime.processors.mem0_memory import Mem0MemoryProcessor
from aithru_agent.settings import AgentLongTermMemorySettings
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


class FakeAddProvider:
    def __init__(self) -> None:
        self.messages = []

    async def search(self, *, run, query: str, limit: int):
        raise AssertionError("write processor must not search")

    async def add_messages(self, *, run, messages):
        del run
        self.messages.append(list(messages))
        return LongTermMemoryAddResult(status="PENDING", event_id="evt_1")

    async def delete_memory(self, *, memory_id: str):
        raise AssertionError("write processor must not delete memory")


async def context_fixture(scopes: list[str]):
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    event_writer = AgentEventWriter(event_store)
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Remember that I prefer concise Chinese summaries.",
        workspace_id=workspace.id,
        scopes=scopes,
        thread_id=thread.id,
    )
    await store.append_message(
        thread_id=thread.id,
        role="user",
        content="Remember that I prefer concise Chinese summaries.",
        run_id=run.id,
    )
    await store.append_message(
        thread_id=thread.id,
        role="assistant",
        content="I will keep that in mind.",
        run_id=run.id,
    )
    await store.update_run(run.id, status=AgentRunStatus.RUNNING)
    completed = await store.update_run(
        run.id,
        status=AgentRunStatus.COMPLETED,
        result={"content": "I will keep that in mind."},
    )
    return AgentRuntimeProcessorContext(
        run=completed,
        store=store,
        event_writer=event_writer,
        event_store=event_store,
        terminal_status=AgentRunStatus.COMPLETED,
    )


async def test_mem0_processor_adds_completed_run_messages() -> None:
    provider = FakeAddProvider()
    processor = Mem0MemoryProcessor(
        provider=provider,
        settings=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key"),
    )
    context = await context_fixture(["agent.memory.write"])

    await processor.after_terminal(context)

    assert len(provider.messages) == 1
    assert [message.role for message in provider.messages[0]] == ["user", "assistant"]
    events = await context.event_store.list_by_run(context.run.id)
    assert [event.type for event in events] == [
        "memory.add.started",
        "memory.add.completed",
    ]
    assert events[-1].payload["event_id"] == "evt_1"


async def test_mem0_processor_skips_without_write_scope() -> None:
    provider = FakeAddProvider()
    processor = Mem0MemoryProcessor(
        provider=provider,
        settings=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key"),
    )
    context = await context_fixture(["agent.memory.read"])

    await processor.after_terminal(context)

    assert provider.messages == []
    events = await context.event_store.list_by_run(context.run.id)
    assert events[-1].type == "memory.add.skipped"
    assert events[-1].payload["reason"] == "missing_memory_write_scope"


async def test_mem0_processor_respects_no_memory_marker() -> None:
    provider = FakeAddProvider()
    processor = Mem0MemoryProcessor(
        provider=provider,
        settings=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key"),
    )
    context = await context_fixture(["agent.memory.write"])
    run = await context.store.update_run(
        context.run.id,
        task_msg="Do not remember this preference.",
    )
    context = AgentRuntimeProcessorContext(
        run=run,
        store=context.store,
        event_writer=context.event_writer,
        event_store=context.event_store,
        terminal_status=AgentRunStatus.COMPLETED,
    )

    await processor.after_terminal(context)

    assert provider.messages == []
    events = await context.event_store.list_by_run(context.run.id)
    assert events[-1].type == "memory.add.skipped"
    assert events[-1].payload["reason"] == "no_memory_marker"
