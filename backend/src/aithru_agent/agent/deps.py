"""Typed dependency container for the native Pydantic AI agent."""

from dataclasses import dataclass

from aithru_agent.capabilities import AithruCapabilityRouter, AgentRunContext
from aithru_agent.domain import AgentRun, AgentSkill
from aithru_agent.persistence.protocols import AgentStore
from aithru_agent.stream import AgentEventWriter


@dataclass(frozen=True)
class PydanticAgentDeps:
    """Dependencies available to Pydantic AI tools and runtime hooks."""

    run: AgentRun
    run_context: AgentRunContext
    event_writer: AgentEventWriter
    capability_router: AithruCapabilityRouter
    store: AgentStore
    skill: AgentSkill | None = None
