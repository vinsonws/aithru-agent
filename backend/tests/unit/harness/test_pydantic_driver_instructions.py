from aithru_agent.domain import AgentSkill
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
