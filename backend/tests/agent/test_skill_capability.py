import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime, PydanticAgentDeps
from aithru_agent.agent.capabilities import SkillInstructionCapability
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.domain import AgentSkill, AgentSkillStatus
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


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
        goal="Create a report.",
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
    )


def test_skill_instruction_capability_builds_active_skill_prompt_section() -> None:
    capability = SkillInstructionCapability([_skill()])

    instructions = capability.get_instructions()

    assert "## Active Aithru Skills" in instructions
    assert "Report" in instructions
    assert "Use active skill instructions." in instructions
    assert "report work" in instructions


@pytest.mark.asyncio
async def test_runtime_adds_skill_instruction_capability_for_active_skill() -> None:
    runtime = AgentRuntime(model=TestModel(call_tools=[], custom_output_text="done"))

    agent = await runtime.build_agent(await _deps(_skill()))

    root_capabilities = getattr(getattr(agent, "_root_capability"), "capabilities")

    assert any(
        isinstance(capability, SkillInstructionCapability)
        for capability in root_capabilities
    )

