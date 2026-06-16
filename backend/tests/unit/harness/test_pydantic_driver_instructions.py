from aithru_agent.domain import AgentMemoryEntry, AgentMemoryPolicy, AgentSkill
from aithru_agent.harness.drivers.pydantic_ai.driver import PydanticAIHarnessDriver


def test_pydantic_driver_combines_base_and_skill_instructions() -> None:
    skill = AgentSkill(
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
    driver = PydanticAIHarnessDriver(instructions="Base instructions.")

    instructions = driver.instructions_for_run(skill)

    assert instructions == "Base instructions.\n\nSkill instructions:\nRead files first. Then write a report."


def test_pydantic_driver_adds_memory_entries_to_instructions() -> None:
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Use relevant memory.",
        allowed_tools=["workspace.list_files"],
        allowed_subagents=[],
        memory_policy=AgentMemoryPolicy(read=True, write=False, scopes=["user"]),
        version="0.1.0",
        status="published",
    )
    memory = AgentMemoryEntry(
        id="memory_1",
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
        created_at="2026-06-16T00:00:00Z",
        updated_at="2026-06-16T00:00:00Z",
    )
    driver = PydanticAIHarnessDriver(instructions="Base instructions.")

    instructions = driver.instructions_for_run(skill, memory_entries=[memory])

    assert "Memory:" in instructions
    assert "- user:preference.language = Prefers Chinese summaries." in instructions
