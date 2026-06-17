import pytest

from aithru_agent.agent import PydanticAgentDeps
from aithru_agent.agent.instructions import InstructionBuilder
from aithru_agent.capabilities import AithruCapabilityRouter
from aithru_agent.domain import (
    AgentMemoryPolicy,
    AgentRunHarnessOptions,
    AgentSkill,
)
from aithru_agent.harness import ContextBuilder
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


def file_report_skill() -> AgentSkill:
    return AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Read files first. Then write a report.",
        allowed_tools=["workspace.list_files"],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )


async def build_deps(
    *,
    store: InMemoryAgentStore,
    skill: AgentSkill | None = None,
    harness_options: AgentRunHarnessOptions | None = None,
) -> PydanticAgentDeps:
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Write a report.",
        workspace_id=workspace.id,
        scopes=["*"],
        harness_options=harness_options,
        skill_id=skill.key if skill else None,
    )
    return PydanticAgentDeps(
        run=run,
        run_context=ContextBuilder().build(run, run.scopes, skill),
        event_writer=AgentEventWriter(InMemoryAgentEventStore()),
        capability_router=AithruCapabilityRouter(adapters=[]),
        store=store,
        skill=skill,
    )


@pytest.mark.asyncio
async def test_instruction_builder_combines_base_and_skill_instructions() -> None:
    deps = await build_deps(store=InMemoryAgentStore(), skill=file_report_skill())

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert instructions == (
        "Base instructions.\n\n"
        "Skill instructions:\nRead files first. Then write a report."
    )


@pytest.mark.asyncio
async def test_instruction_builder_adds_memory_entries_to_instructions() -> None:
    store = InMemoryAgentStore()
    skill = file_report_skill().model_copy(
        update={
            "instructions": "Use relevant memory.",
            "memory_policy": AgentMemoryPolicy(read=True, write=False, scopes=["user"]),
        }
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
    )
    deps = await build_deps(store=store, skill=skill)

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "Memory:" in instructions
    assert "- user:preference.language = Prefers Chinese summaries." in instructions


@pytest.mark.asyncio
async def test_instruction_builder_adds_run_harness_instructions() -> None:
    deps = await build_deps(
        store=InMemoryAgentStore(),
        harness_options=AgentRunHarnessOptions(instructions="Use terse bullet points."),
    )

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert instructions == "Base instructions.\n\nRun instructions:\nUse terse bullet points."
