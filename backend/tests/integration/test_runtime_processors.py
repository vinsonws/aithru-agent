import pytest

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.domain import AgentRunRetryPolicy, AgentRunStatus
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
    AgentRuntimeProcessorRunner,
)
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.worker.runner import AgentWorkerRunner


class ShouldNotRunRuntime(AgentRuntime):
    async def run(self, goal: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del goal, deps
        raise AssertionError("model should not run after a before_model pause")


class DoneRuntime(AgentRuntime):
    async def run(self, goal: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del goal, deps
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
        goal="Pause before model",
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
        goal="Retry processor failure",
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
        goal="Record after terminal",
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
        goal="Complete despite processor failure",
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
