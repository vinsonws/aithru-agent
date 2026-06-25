import asyncio

import pytest

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.api.dependencies import ApiDependencies
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.memory import LongTermMemoryAddResult, LongTermMemorySearchResult
from aithru_agent.runtime.processors.mem0_memory import Mem0MemoryProcessor
from aithru_agent.settings import AgentLongTermMemorySettings
from aithru_agent.capabilities import AithruCapabilityRouter, AgentRunContext, ToolPolicy
from aithru_agent.domain import AgentRunRetryPolicy, AgentRunStatus
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
    AgentRuntimeProcessorRunner,
    MemoryExtractionProcessor,
)
from aithru_agent.runtime.processors.clarification import ClarificationPreflightProcessor
from aithru_agent.runtime.processors.summarization import ContextSummarizationProcessor
from aithru_agent.runtime.processors.title import ThreadTitleProcessor
from aithru_agent.settings import AgentSettings
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.worker.runner import AgentWorkerRunner


class ShouldNotRunRuntime(AgentRuntime):
    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg, deps
        raise AssertionError("model should not run after a before_model pause")


class DoneRuntime(AgentRuntime):
    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg, deps
        return AgentRuntimeResult(content="done")


class PauseBeforeModelProcessor(AgentRuntimeProcessor):
    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        paused = await context.store.update_run(
            context.run.id,
            status=AgentRunStatus.WAITING_INPUT,
        )
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={
                "status": "waiting_input",
                "reason": "runtime_processor",
            },
        )
        return AgentRuntimeProcessorDecision(paused_run=paused)


class FailingBeforeModelProcessor(AgentRuntimeProcessor):
    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        del context
        raise RuntimeError("processor setup failed")


class RecordingAfterTerminalProcessor(AgentRuntimeProcessor):
    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="runtime.processor.recorded",
            source={"kind": "harness"},
            visibility="debug",
            payload={"status": context.terminal_status},
        )
        return AgentRuntimeProcessorDecision()


class FailingAfterTerminalProcessor(AgentRuntimeProcessor):
    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        del context
        raise RuntimeError("after terminal failed")


def make_runner(
    processor_runner: AgentRuntimeProcessorRunner,
    *,
    agent_runtime: AgentRuntime | None = None,
) -> tuple[AgentWorkerRunner, InMemoryAgentStore, InMemoryAgentEventStore]:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    runner = AgentWorkerRunner(
        store=store,
        event_writer=writer,
        event_store=event_store,
        capability_router=AithruCapabilityRouter(
            adapters=[],
            policy=ToolPolicy(require_approval_for_risk=[]),
        ),
        agent_runtime=agent_runtime or DoneRuntime(),
        processor_runner=processor_runner,
    )
    return runner, store, event_store


@pytest.mark.asyncio
async def test_before_model_processor_can_pause_before_model_started() -> None:
    runner, store, event_store = make_runner(
        AgentRuntimeProcessorRunner(
            processors=[PauseBeforeModelProcessor()],
        ),
        agent_runtime=ShouldNotRunRuntime(),
    )

    run = await runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Pause before model",
        scopes=["*"],
    )
    event_types = [event.type for event in await event_store.list_by_run(run.id)]

    assert run.status == AgentRunStatus.WAITING_INPUT
    assert event_types == [
        "run.created",
        "run.started",
        "run.paused",
    ]
    assert "model.started" not in event_types


def test_application_wires_runtime_processors_from_settings() -> None:
    enabled = create_agent_runtime(
        agent_runtime=DoneRuntime(),
        settings=AgentSettings(model="test"),
    )
    disabled = create_agent_runtime(
        agent_runtime=DoneRuntime(),
        settings=AgentSettings(
            model="test",
            processors={
                "clarification_enabled": False,
                "title_generation_enabled": False,
                "title_max_words": 6,
                "summarization_enabled": False,
                "summarization_min_message_count": 9,
                "memory_extraction_enabled": False,
            },
        ),
    )

    assert [
        type(processor) for processor in enabled.processor_runner.processors
    ] == [
        ClarificationPreflightProcessor,
        ThreadTitleProcessor,
        ContextSummarizationProcessor,
        MemoryExtractionProcessor,
    ]
    assert disabled.processor_runner.processors == []


@pytest.mark.asyncio
async def test_before_model_processor_exception_uses_retry_failure_path() -> None:
    runner, store, event_store = make_runner(
        AgentRuntimeProcessorRunner(
            processors=[FailingBeforeModelProcessor()],
        ),
        agent_runtime=ShouldNotRunRuntime(),
    )

    run = await runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Retry processor failure",
        scopes=["*"],
        retry_policy=AgentRunRetryPolicy(max_attempts=2, initial_delay_seconds=30),
    )
    stored = await store.get_run(run.id)
    event_types = [event.type for event in await event_store.list_by_run(run.id)]

    assert run.status == AgentRunStatus.QUEUED
    assert stored.status == AgentRunStatus.QUEUED
    assert event_types[-1] == "run.retry.scheduled"
    assert "model.started" not in event_types
    assert "run.failed" not in event_types


@pytest.mark.asyncio
async def test_after_terminal_processor_event_precedes_run_completed() -> None:
    runner, _, event_store = make_runner(
        AgentRuntimeProcessorRunner(
            processors=[RecordingAfterTerminalProcessor()],
        )
    )

    run = await runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Record after terminal",
        scopes=["*"],
    )
    events = await event_store.list_by_run(run.id)
    event_types = [event.type for event in events]

    assert run.status == AgentRunStatus.COMPLETED
    assert event_types.index("runtime.processor.recorded") < event_types.index("run.completed")
    assert event_types[-1] == "run.completed"


@pytest.mark.asyncio
async def test_after_terminal_processor_exception_is_recorded_without_raising() -> None:
    runner, store, event_store = make_runner(
        AgentRuntimeProcessorRunner(
            processors=[FailingAfterTerminalProcessor()],
        )
    )

    run = await runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Complete despite processor failure",
        scopes=["*"],
    )
    stored = await store.get_run(run.id)
    events = await event_store.list_by_run(run.id)
    event_types = [event.type for event in events]
    failure_event = next(event for event in events if event.type == "runtime.processor.failed")

    assert run.status == AgentRunStatus.COMPLETED
    assert stored.status == AgentRunStatus.COMPLETED
    assert event_types[-1] == "run.completed"
    assert failure_event.visibility == "debug"
    assert failure_event.payload["hook"] == "after_terminal"
    assert failure_event.payload["processor"] == "FailingAfterTerminalProcessor"
    assert failure_event.payload["error"]["message"] == "after terminal failed"


@pytest.mark.asyncio
async def test_follow_run_events_waits_for_terminal_stream_event_after_terminal_state() -> None:
    runtime = create_agent_runtime(agent_runtime=DoneRuntime())
    deps = ApiDependencies(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Stream terminal race",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    await runtime.store.update_run(run.id, status=AgentRunStatus.RUNNING)
    await runtime.event_writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="run.started",
        source={"kind": "harness"},
        payload={"status": "running"},
    )

    async def collect_followed_events() -> list[str]:
        return [
            chunk
            async for chunk in deps.follow_run_events(
                run.id,
                after_sequence=1,
                poll_interval_seconds=0.01,
                timeout_seconds=1,
            )
        ]

    stream_task = asyncio.create_task(collect_followed_events())
    await asyncio.sleep(0.03)
    assert not stream_task.done()

    await runtime.store.update_run(
        run.id,
        status=AgentRunStatus.COMPLETED,
        completed_at="2026-06-22T00:00:00Z",
    )
    await asyncio.sleep(0.05)
    assert not stream_task.done()

    await runtime.event_writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="runtime.processor.recorded",
        source={"kind": "harness"},
        visibility="debug",
        payload={"status": "completed"},
    )
    await runtime.event_writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="run.completed",
        source={"kind": "harness"},
        payload={"status": "completed"},
    )
    stream_text = "".join(await asyncio.wait_for(stream_task, timeout=1))

    assert "event: runtime.processor.recorded" in stream_text
    assert "event: run.completed" in stream_text
    assert stream_text.index("event: runtime.processor.recorded") < stream_text.index(
        "event: run.completed"
    )


@pytest.mark.asyncio
async def test_follow_run_events_returns_promptly_when_cursor_has_seen_terminal_event() -> None:
    runtime = create_agent_runtime(agent_runtime=DoneRuntime())
    deps = ApiDependencies(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Reconnect after terminal event",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    await runtime.store.update_run(run.id, status=AgentRunStatus.RUNNING)
    await runtime.store.update_run(
        run.id,
        status=AgentRunStatus.COMPLETED,
        completed_at="2026-06-22T00:00:00Z",
    )
    terminal_event = await runtime.event_writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="run.completed",
        source={"kind": "harness"},
        payload={"status": "completed"},
    )

    chunks = await asyncio.wait_for(
        _collect_followed_events(
            deps,
            run.id,
            after_sequence=terminal_event.sequence,
            timeout_seconds=5,
        ),
        timeout=0.2,
    )

    assert chunks == []


class AppWiringMem0Provider:
    async def search(self, *, run, query: str, limit: int):
        return []

    async def add_messages(self, *, run, messages):
        return LongTermMemoryAddResult(status="PENDING", event_id="evt_app")

    async def delete_memory(self, *, memory_id: str, org_id: str, actor_user_id: str):
        del org_id, actor_user_id
        raise AssertionError("app wiring test must not delete memory")


def test_mem0_provider_mode_registers_mem0_processor_instead_of_candidate_processor() -> None:
    app = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            long_term_memory=AgentLongTermMemorySettings(
                provider="mem0",
                mem0_api_key="mem0-key",
            ),
        ),
        long_term_memory_provider=AppWiringMem0Provider(),
    )

    processor_names = [
        processor.__class__.__name__
        for processor in app.processor_runner.processors
    ]

    assert "Mem0MemoryProcessor" in processor_names
    assert "MemoryExtractionProcessor" not in processor_names


@pytest.mark.asyncio
async def test_mem0_provider_mode_does_not_expose_local_memory_tools() -> None:
    app = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            long_term_memory=AgentLongTermMemorySettings(
                provider="mem0",
                mem0_api_key="mem0-key",
            ),
        ),
        long_term_memory_provider=AppWiringMem0Provider(),
    )

    tools = await app.capability_router.list_tools(
        AgentRunContext(
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
            scopes=["agent.memory.read", "agent.memory.write"],
        )
    )

    tool_names = {tool.name for tool in tools}
    assert "memory.search" not in tool_names
    assert "memory.remember" not in tool_names


async def _collect_followed_events(
    deps: ApiDependencies,
    run_id: str,
    *,
    after_sequence: int,
    timeout_seconds: float,
) -> list[str]:
    return [
        chunk
        async for chunk in deps.follow_run_events(
            run_id,
            after_sequence=after_sequence,
            poll_interval_seconds=0.01,
            timeout_seconds=timeout_seconds,
        )
    ]
