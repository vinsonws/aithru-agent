from __future__ import annotations

from dataclasses import dataclass

from aithru_agent.domain import AgentRun, AgentRunStatus, AgentSkill
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.stream import AgentEventWriter


@dataclass(frozen=True)
class AgentRuntimeProcessorContext:
    run: AgentRun
    store: AgentStore
    event_writer: AgentEventWriter
    event_store: AgentEventStore | None = None
    skill: AgentSkill | None = None
    terminal_status: AgentRunStatus | None = None


@dataclass(frozen=True)
class AgentRuntimeProcessorDecision:
    paused_run: AgentRun | None = None
    replaced_run: AgentRun | None = None

    @property
    def should_stop(self) -> bool:
        return self.paused_run is not None or self.replaced_run is not None


class AgentRuntimeProcessor:
    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        del context
        return AgentRuntimeProcessorDecision()

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        del context
        return AgentRuntimeProcessorDecision()
