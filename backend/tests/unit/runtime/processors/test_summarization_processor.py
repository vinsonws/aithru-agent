import pytest

from aithru_agent.domain import AgentRunStatus
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors.base import AgentRuntimeProcessorContext
from aithru_agent.runtime.processors.summarization import ContextSummarizationProcessor
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_completed_threaded_run_creates_context_summary_and_event() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Summarize durable context",
        workspace_id=workspace.id,
        thread_id=thread.id,
    )
    for index, content in enumerate(
        [
            "Need a concise backend parity report.",
            "Confirm the harness boundary stays explicit.",
            "Summaries are context facts, not workflow checkpoints.",
            "Older messages may be dropped by the context packet budget.",
            "The summary should be deterministic and local.",
            "Persist it so future runs can recover semantic context.",
        ]
    ):
        await store.append_message(
            thread_id=thread.id,
            role="user" if index % 2 == 0 else "assistant",
            content=content,
            run_id=run.id,
        )
    completed_run = run.model_copy(update={"status": AgentRunStatus.COMPLETED})

    decision = await ContextSummarizationProcessor().after_terminal(
        AgentRuntimeProcessorContext(
            run=completed_run,
            store=store,
            event_writer=writer,
            event_store=event_store,
            terminal_status=AgentRunStatus.COMPLETED,
        )
    )

    summaries = await store.list_context_summaries(org_id=run.org_id, thread_id=thread.id)
    events = await event_store.list_by_run(run.id)
    assert decision.should_stop is False
    assert len(summaries) == 1
    assert summaries[0].id == f"summary_{run.id}"
    assert summaries[0].org_id == "org_1"
    assert summaries[0].thread_id == thread.id
    assert summaries[0].run_id == run.id
    assert summaries[0].source == "semantic_processor"
    assert summaries[0].message_count == 6
    assert summaries[0].summary.startswith("user: Need a concise backend parity report.")
    assert [event.type for event in events] == ["context.summary.created"]
    assert events[0].visibility == "debug"
    assert events[0].payload["summary_id"] == f"summary_{run.id}"
    assert events[0].payload["message_count"] == 6


@pytest.mark.asyncio
async def test_processor_no_ops_without_thread_or_with_too_few_messages() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run_without_thread = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="No thread",
        workspace_id=workspace.id,
    )
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    run_with_few_messages = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Too few messages",
        workspace_id=workspace.id,
        thread_id=thread.id,
    )
    for index in range(5):
        await store.append_message(
            thread_id=thread.id,
            role="user",
            content=f"message {index}",
            run_id=run_with_few_messages.id,
        )
    processor = ContextSummarizationProcessor()

    for run in (run_without_thread, run_with_few_messages):
        await processor.after_terminal(
            AgentRuntimeProcessorContext(
                run=run.model_copy(update={"status": AgentRunStatus.COMPLETED}),
                store=store,
                event_writer=writer,
                event_store=event_store,
                terminal_status=AgentRunStatus.COMPLETED,
            )
        )

    assert await store.list_context_summaries(org_id="org_1") == []
    assert await event_store.list_by_run(run_without_thread.id) == []
    assert await event_store.list_by_run(run_with_few_messages.id) == []


@pytest.mark.asyncio
async def test_processor_no_ops_for_failed_or_cancelled_terminal_runs() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    failed_run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Failed run",
        workspace_id=workspace.id,
        thread_id=thread.id,
    )
    cancelled_run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Cancelled run",
        workspace_id=workspace.id,
        thread_id=thread.id,
    )
    for index in range(6):
        await store.append_message(
            thread_id=thread.id,
            role="user",
            content=f"message {index}",
        )
    processor = ContextSummarizationProcessor()

    for run, status in (
        (failed_run, AgentRunStatus.FAILED),
        (cancelled_run, AgentRunStatus.CANCELLED),
    ):
        await processor.after_terminal(
            AgentRuntimeProcessorContext(
                run=run.model_copy(update={"status": status}),
                store=store,
                event_writer=writer,
                event_store=event_store,
                terminal_status=status,
            )
        )

    assert await store.list_context_summaries(org_id="org_1", thread_id=thread.id) == []
    assert await event_store.list_by_run(failed_run.id) == []
    assert await event_store.list_by_run(cancelled_run.id) == []
