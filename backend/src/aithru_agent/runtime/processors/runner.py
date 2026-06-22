from __future__ import annotations

from collections.abc import Sequence

from aithru_agent.domain import AgentRun, AgentRunStatus, AgentSkill
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.stream import AgentEventWriter

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


class AgentRuntimeProcessorRunner:
    def __init__(
        self,
        processors: Sequence[AgentRuntimeProcessor] | None = None,
    ) -> None:
        self._processors = list(processors or [])

    @property
    def processors(self) -> list[AgentRuntimeProcessor]:
        return list(self._processors)

    async def before_model(
        self,
        *,
        run: AgentRun,
        store: AgentStore,
        event_writer: AgentEventWriter,
        event_store: AgentEventStore | None = None,
        skill: AgentSkill | None = None,
    ) -> AgentRuntimeProcessorDecision:
        context = AgentRuntimeProcessorContext(
            run=run,
            store=store,
            event_writer=event_writer,
            event_store=event_store,
            skill=skill,
        )
        for processor in self._processors:
            decision = await processor.before_model(context)
            if decision.should_stop:
                return decision
        return AgentRuntimeProcessorDecision()

    async def after_terminal(
        self,
        *,
        run: AgentRun,
        store: AgentStore,
        event_writer: AgentEventWriter,
        event_store: AgentEventStore | None = None,
        skill: AgentSkill | None = None,
        terminal_status: AgentRunStatus,
    ) -> AgentRuntimeProcessorDecision:
        context = AgentRuntimeProcessorContext(
            run=run,
            store=store,
            event_writer=event_writer,
            event_store=event_store,
            skill=skill,
            terminal_status=terminal_status,
        )
        latest_decision = AgentRuntimeProcessorDecision()
        for processor in self._processors:
            try:
                latest_decision = await processor.after_terminal(context)
            except Exception as exc:
                await event_writer.write(
                    run_id=run.id,
                    thread_id=run.thread_id,
                    type="runtime.processor.failed",
                    source={"kind": "harness"},
                    visibility="debug",
                    payload={
                        "hook": "after_terminal",
                        "processor": processor.__class__.__name__,
                        "error": _error_payload(exc),
                    },
                )
        return latest_decision


def _error_payload(error: Exception) -> dict[str, str]:
    return {"message": str(error)}
