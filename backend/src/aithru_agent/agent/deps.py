"""Typed dependency container for the native Pydantic AI agent."""

from dataclasses import dataclass, field

from aithru_agent.capabilities import AithruCapabilityRouter, AgentRunContext
from aithru_agent.domain import AgentRun, AgentRunContextPacket, AgentSkill
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.skills.packages import SkillPackage
from aithru_agent.stream import AgentEventWriter


@dataclass(frozen=True)
class PydanticAgentDeps:
    """Dependencies available to Pydantic AI tools and runtime hooks."""

    run: AgentRun
    run_context: AgentRunContext
    event_writer: AgentEventWriter
    capability_router: AithruCapabilityRouter
    store: AgentStore
    event_store: AgentEventStore | None = None
    skill: AgentSkill | None = None
    context_packet: AgentRunContextPacket | None = None
    tool_name_aliases: dict[str, str] = field(default_factory=dict)
    visible_skill_packages: dict[str, SkillPackage] = field(default_factory=dict)
    explicit_skill_key: str | None = None
    emitted_skill_activation_keys: set[str] = field(default_factory=set)
