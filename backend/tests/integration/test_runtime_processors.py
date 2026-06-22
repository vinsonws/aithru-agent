import pytest

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.domain import AgentRunStatus
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


@pytest.mark.asyncio
async def test_before_model_processor_can_pause_before_model_started() -> None:
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
        agent_runtime=ShouldNotRunRuntime(),
        processor_runner=AgentRuntimeProcessorRunner(
            processors=[PauseBeforeModelProcessor()],
        ),
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
