"""Tests for the skill package domain and parser."""

from aithru_agent.domain import AgentSkillConfiguration, AgentSkillRegistrySource
from aithru_agent.skills.packages import parse_skill_package, render_skill_md


def test_parse_skill_package_uses_frontmatter_for_discovery_and_body_for_instructions() -> None:
    package = parse_skill_package(
        key="file-report",
        org_id="org_1",
        owner_user_id="user_1",
        source=AgentSkillRegistrySource.USER,
        skill_md="""---
name: File Report
description: Use for concise reports from workspace files.
---

# File Report

Read the relevant files, then write a short report.
""",
        policy=AgentSkillConfiguration(
            instructions="",
            allowed_tools=["workspace.read_file", "artifact.create"],
            denied_tools=[],
            allowed_subagents=[],
        ),
    )

    assert package.key == "file-report"
    assert package.metadata.name == "File Report"
    assert package.metadata.description == "Use for concise reports from workspace files."
    assert "Read the relevant files" in package.instructions
    assert package.discovery_description == "File Report: Use for concise reports from workspace files."


def test_render_user_skill_md_round_trips_metadata_and_body() -> None:
    skill_md = render_skill_md(
        name="File Report",
        description="Use for concise reports from workspace files.",
        body="# File Report\n\nWrite from evidence.",
    )

    package = parse_skill_package(
        key="file-report",
        org_id="org_1",
        owner_user_id="user_1",
        source=AgentSkillRegistrySource.USER,
        skill_md=skill_md,
        policy=AgentSkillConfiguration(instructions="", allowed_tools=[], allowed_subagents=[]),
    )

    assert package.metadata.name == "File Report"
    assert package.instructions == "# File Report\n\nWrite from evidence."


def test_skill_package_source_user_sets_owner() -> None:
    package = parse_skill_package(
        key="my-skill",
        org_id="org_1",
        owner_user_id="user_42",
        source=AgentSkillRegistrySource.USER,
        skill_md="""---
name: My Skill
description: A test skill.
---

Body.
""",
        policy=AgentSkillConfiguration(instructions="", allowed_tools=[], allowed_subagents=[]),
    )

    assert package.source == AgentSkillRegistrySource.USER
    assert package.owner_user_id == "user_42"
    assert package.read_only is False


def test_skill_package_builtin_is_read_only() -> None:
    package = parse_skill_package(
        key="deep-research",
        org_id="org_1",
        owner_user_id=None,
        source=AgentSkillRegistrySource.BUILTIN,
        skill_md="""---
name: Deep Research
description: Research skill.
---

Body.
""",
        policy=AgentSkillConfiguration(instructions="", allowed_tools=[], allowed_subagents=[]),
        read_only=True,
    )

    assert package.source == AgentSkillRegistrySource.BUILTIN
    assert package.read_only is True
    assert package.owner_user_id is None


def test_skill_package_policy_instructions_override() -> None:
    skill_md = """---
name: Override Test
description: Test instructions override.
---

# Skill Body

These are the instructions.
"""

    package = parse_skill_package(
        key="override",
        org_id="org_1",
        owner_user_id=None,
        source=AgentSkillRegistrySource.BUILTIN,
        skill_md=skill_md,
        policy=AgentSkillConfiguration(
            instructions="ignored",
            allowed_tools=["workspace.read_file"],
            allowed_subagents=[],
        ),
    )

    assert package.instructions == "# Skill Body\n\nThese are the instructions."
    assert package.policy.instructions == "# Skill Body\n\nThese are the instructions."
    assert package.policy.allowed_tools == ["workspace.read_file"]
