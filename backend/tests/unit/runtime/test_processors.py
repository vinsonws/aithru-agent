import pytest

from aithru_agent.domain import AgentRunSource, AgentRunStatus
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
    AgentRuntimeProcessorRunner,
)
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


class RecordingProcessor(AgentRuntimeProcessor):
    def __init__(self, name: str, sink: list[str]) -> None:
        self.name = name
        self._sink = sink

    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        self._sink.append(f"before:{self.name}:{context.run.id}")
        return AgentRuntimeProcessorDecision()

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        self._sink.append(f"after:{self.name}:{context.run.id}:{context.terminal_status}")
        return AgentRuntimeProcessorDecision()


@pytest.mark.asyncio
async def test_processor_runner_invokes_hooks_in_order() -> None:
    store = InMemoryAgentStore()
    events = InMemoryAgentEventStore()
    writer = AgentEventWriter(events)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.API,
        task_msg="Summarize the workspace",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    sink: list[str] = []
    runner = AgentRuntimeProcessorRunner(
        processors=[
            RecordingProcessor("first", sink),
            RecordingProcessor("second", sink),
        ]
    )

    await runner.before_model(
        run=run,
        store=store,
        event_writer=writer,
        event_store=events,
        skill=None,
    )
    completed = run.model_copy(update={"status": AgentRunStatus.COMPLETED})
    await runner.after_terminal(
        run=completed,
        store=store,
        event_writer=writer,
        event_store=events,
        skill=None,
        terminal_status=AgentRunStatus.COMPLETED,
    )

    assert sink == [
        "before:first:run_1",
        "before:second:run_1",
        "after:first:run_1:completed",
        "after:second:run_1:completed",
    ]
