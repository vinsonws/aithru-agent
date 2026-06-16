import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentSkill
from aithru_agent.harness.drivers.pydantic_ai import PydanticAIHarnessDriver
from aithru_agent.harness.drivers.scripted import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.skills.resolver import InMemorySkillResolver
from pydantic_ai.models.test import TestModel


def file_report_skill(allowed_tools: list[str]) -> AgentSkill:
    return AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Only use the allowed file report tools.",
        allowed_tools=allowed_tools,
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )


@pytest.mark.asyncio
async def test_worker_denies_scripted_tool_not_allowed_by_skill() -> None:
    runtime = create_agent_runtime(
        driver=ScriptedHarnessDriver(
            [
                ScriptedStep.tool("workspace.write_file", {"path": "/x.md", "content": "x"}),
                ScriptedStep.finish(),
            ]
        ),
        skill_resolver=InMemorySkillResolver([file_report_skill(["workspace.read_file"])]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Try write",
        scopes=["*"],
        skill_id="file-report",
    )
    events = await runtime.event_store.list_by_run(run.id)

    assert "tool.denied" in [event.type for event in events]
    assert await runtime.store.list_workspace_files(run.workspace_id) == []


@pytest.mark.asyncio
async def test_pydantic_driver_exposes_only_skill_allowed_tools() -> None:
    runtime = create_agent_runtime(
        driver=PydanticAIHarnessDriver(
            model=TestModel(call_tools=["workspace.list_files"], custom_output_text="done")
        ),
        skill_resolver=InMemorySkillResolver([file_report_skill(["workspace.list_files"])]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Read file",
        scopes=["*"],
        skill_id="file-report",
    )
    events = await runtime.event_store.list_by_run(run.id)

    assert "tool.proposed" in [event.type for event in events]
    assert all(
        event.payload.get("tool_name") != "workspace.write_file"
        for event in events
        if isinstance(event.payload, dict)
    )
