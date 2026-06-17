import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime
from aithru_agent.agent.skills import SkillRegistry, parse_skill_md
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.settings import AgentSettings


SKILL_MD = """---
name: report-helper
description: Helps with report work.
tags: [report]
---

# Report Helper

Use concise report instructions.

## Activation
report report report

## Tool Policy
Allowed: workspace.list_files
Denied: workspace.write_file
"""


def test_parse_skill_md_extracts_progressive_skill_policy() -> None:
    skill = parse_skill_md(SKILL_MD)

    assert skill.name == "report-helper"
    assert skill.description == "Helps with report work."
    assert skill.tags == ["report"]
    assert skill.when_to_use_summary == "report report report"
    assert skill.allowed_tools == ["workspace.list_files"]
    assert skill.denied_tools == ["workspace.write_file"]
    assert "Use concise report instructions." in skill.instructions


@pytest.mark.asyncio
async def test_agent_runtime_activates_progressive_skill_and_filters_tools() -> None:
    registry = SkillRegistry()
    registry.load_skill_from_content("report-helper", SKILL_MD)
    runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools="all", custom_output_text="done"),
            skill_registry=registry,
        ),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Create a report.",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    tool_names = [
        event.payload["tool_name"]
        for event in events
        if event.type == "tool.proposed"
    ]

    assert any(event.type == "skill.activated" for event in events)
    assert tool_names == ["workspace.list_files"]
