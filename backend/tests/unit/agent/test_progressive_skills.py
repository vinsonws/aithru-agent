"""Tests for skill MD parsing and capability-based activation."""

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from aithru_agent.agent.capabilities.toolset import AithruToolset
from aithru_agent.agent.skills import parse_skill_md
from aithru_agent.capabilities import AgentRunContext
from aithru_agent.domain import AgentSkillConfiguration, AgentRunStatus
from aithru_agent.skills.package_store import SkillActor
from aithru_agent.skills.packages import parse_skill_package
from aithru_agent.domain import AgentSkillRegistrySource
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.agent.deps import PydanticAgentDeps


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
async def test_loaded_skill_policy_filters_aithru_toolset_with_package() -> None:
    deps = await _deps_with_visible_packages(["report-helper"])
    ctx = RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        loaded_capability_ids={"skill:report-helper"},
    )

    tools = await AithruToolset().get_tools(ctx)

    assert list(tools) == ["workspace.list_files"]


def _package(key: str, allowed_tools: list[str]) -> object:
    name = key.capitalize().replace("-", " ")
    return parse_skill_package(
        key=key,
        org_id="org_1",
        owner_user_id="user_1",
        source=AgentSkillRegistrySource.USER,
        skill_md=f"""---
name: {name}
description: {key} description.
---

{key} body.
""",
        policy=AgentSkillConfiguration(instructions="", allowed_tools=allowed_tools, allowed_subagents=[]),
    )


async def _fake_list_tools(self, ctx: object) -> list:
    from aithru_agent.capabilities import AgentRunContext
    from aithru_agent.domain import AgentToolApprovalPolicy, AgentToolDescriptor, AgentToolKind, AgentToolRiskLevel

    allowed = None
    if isinstance(ctx, AgentRunContext) and ctx.allowed_tools is not None:
        allowed = set(ctx.allowed_tools)
    all_tools = [
        AgentToolDescriptor(
            name="workspace.list_files",
            kind=AgentToolKind.LOCAL_TOOL,
            description="List files.",
            input_schema={},
            output_schema={},
            risk_level=AgentToolRiskLevel.SAFE,
            required_scopes=[],
            approval_policy=AgentToolApprovalPolicy.NEVER,
        ),
        AgentToolDescriptor(
            name="workspace.write_file",
            kind=AgentToolKind.LOCAL_TOOL,
            description="Write a file.",
            input_schema={},
            output_schema={},
            risk_level=AgentToolRiskLevel.SAFE,
            required_scopes=[],
            approval_policy=AgentToolApprovalPolicy.NEVER,
        ),
    ]
    if allowed is not None:
        return [t for t in all_tools if t.name in allowed]
    return all_tools


async def _fake_requires_approval(self, name: str, ctx: object) -> bool:
    return False


async def _deps_with_visible_packages(keys: list[str]) -> PydanticAgentDeps:
    from datetime import UTC, datetime

    from aithru_agent.capabilities import AgentRunContext

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    store = type("FakeStore", (), {"get_run": lambda self, rid: None})()
    run = type(
        "FakeRun",
        (),
        {
            "id": "run_1",
            "org_id": "org_1",
            "actor_user_id": "user_1",
            "source": "api",
            "task_msg": "Create a report.",
            "workspace_id": "ws_1",
            "thread_id": None,
            "skill_id": None,
            "scopes": ["*"],
            "status": AgentRunStatus.RUNNING,
            "started_at": now,
        },
    )
    return PydanticAgentDeps(
        run=run,  # type: ignore[arg-type]
        run_context=AgentRunContext(
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="ws_1",
        ),
        event_writer=AgentEventWriter(InMemoryAgentEventStore()),
        capability_router=type("FakeRouter", (), {"list_tools": _fake_list_tools, "requires_approval_for_tool": _fake_requires_approval})(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        visible_skill_packages={key: _package(key, ["workspace.list_files"]) for key in keys},
    )
