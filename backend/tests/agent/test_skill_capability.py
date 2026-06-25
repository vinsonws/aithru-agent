"""Tests for skill capabilities in Pydantic AI agent assembly."""

import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime, PydanticAgentDeps
from aithru_agent.agent.capabilities import AithruSkillCapability, skill_capability_id
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.domain import AgentSkill, AgentSkillStatus
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.skills.packages import SkillPackage, parse_skill_package
from aithru_agent.domain import AgentSkillConfiguration, AgentSkillRegistrySource
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


def _package(key: str = "report") -> SkillPackage:
    name = key.capitalize()
    return parse_skill_package(
        key=key,
        org_id="org_1",
        owner_user_id="user_1",
        source=AgentSkillRegistrySource.USER,
        skill_md=f"""---
name: {name}
description: Writes evidence-backed reports.
---

Use active skill instructions.
""",
        policy=AgentSkillConfiguration(
            instructions="",
            allowed_tools=[],
            allowed_subagents=[],
        ),
    )


def _skill() -> AgentSkill:
    return AgentSkill(
        id="skill_report",
        org_id="org_1",
        key="report",
        name="Report",
        description="Writes evidence-backed reports.",
        instructions="Use active skill instructions.",
        when_to_use="report work",
        allowed_tools=[],
        denied_tools=[],
        allowed_subagents=[],
        version="0.1.0",
        status=AgentSkillStatus.PUBLISHED,
        enabled=True,
    )


async def _deps(skill: AgentSkill) -> PydanticAgentDeps:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Create a report.",
        workspace_id=workspace.id,
        skill_id=skill.id,
    )
    return PydanticAgentDeps(
        run=run,
        run_context=AgentRunContext(
            run_id=run.id,
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id=workspace.id,
            skill_id=skill.id,
            scopes=["*"],
        ),
        event_writer=writer,
        capability_router=AithruCapabilityRouter(
            adapters=[],
            policy=ToolPolicy(require_approval_for_risk=[]),
        ),
        store=store,
        skill=skill,
        visible_skill_packages={"report": _package(key="report")},
    )


def test_skill_capability_id_format() -> None:
    assert skill_capability_id("file-report") == "skill:file-report"
    assert skill_capability_id("deep-research") == "skill:deep-research"


@pytest.mark.asyncio
async def test_runtime_adds_skill_capabilities_for_visible_packages() -> None:
    runtime = AgentRuntime(model=TestModel(call_tools=[], custom_output_text="done"))

    agent = await runtime.build_agent(await _deps(_skill()))

    root_capabilities = getattr(getattr(agent, "_root_capability"), "capabilities")

    assert any(
        getattr(capability, "id", None) == "skill:report"
        and getattr(capability, "defer_loading", None) is True
        for capability in root_capabilities
    )
