from pathlib import Path

from aithru_agent.domain import AgentSkillStatus
from aithru_agent.harness.context_builder import ContextBuilder
from aithru_agent.skills.loader import FileSkillLoader


def test_file_skill_loader_loads_enabled_skill_package_from_skill_md(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "public" / "file-writer"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: File Writer
description: Writes concise reports from workspace evidence.
key: file-writer
id: skill_file_writer
org_id: org_1
version: 0.2.0
status: published
enabled: true
---

# File Writer

Use workspace evidence and produce concise reports.

## Activation
file report evidence

## Tool Policy
Allowed: workspace.read_file, artifact.create, sandbox.run_python
Denied: sandbox.run_python
""",
        encoding="utf-8",
    )
    (skill_dir / "resources").mkdir()
    (skill_dir / "scripts").mkdir()
    (skill_dir / "examples").mkdir()

    loader = FileSkillLoader(tmp_path / "skills")

    skill = loader.resolve("file-writer")

    assert skill is not None
    assert skill.id == "skill_file_writer"
    assert skill.org_id == "org_1"
    assert skill.key == "file-writer"
    assert skill.name == "File Writer"
    assert skill.description == "Writes concise reports from workspace evidence."
    assert skill.version == "0.2.0"
    assert skill.status == AgentSkillStatus.PUBLISHED
    assert skill.enabled is True
    assert "Use workspace evidence" in skill.instructions
    assert skill.when_to_use == "file report evidence"
    assert skill.allowed_tools == [
        "workspace.read_file",
        "artifact.create",
        "sandbox.run_python",
    ]
    assert skill.denied_tools == ["sandbox.run_python"]


def test_file_skill_loader_ignores_disabled_skill_package(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "custom" / "disabled"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: Disabled Skill
description: Disabled.
key: disabled
id: skill_disabled
org_id: org_1
version: 0.1.0
status: published
enabled: false
---

This should not be active.
""",
        encoding="utf-8",
    )

    loader = FileSkillLoader(tmp_path / "skills")

    assert loader.resolve("disabled") is None
    assert loader.list_skills() == []


def test_skill_denied_tools_are_removed_from_run_context(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "public" / "policy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: Policy Skill
key: policy
id: skill_policy
org_id: org_1
version: 0.1.0
status: published
enabled: true
---

## Tool Policy
Allowed: workspace.read_file, artifact.create, sandbox.run_python
Denied: artifact.create
""",
        encoding="utf-8",
    )
    skill = FileSkillLoader(tmp_path / "skills").resolve("policy")
    assert skill is not None

    context = ContextBuilder().build(
        run=type(
            "Run",
            (),
            {
                "id": "run_1",
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "workspace_id": "workspace_1",
                "thread_id": None,
                "skill_id": skill.id,
            },
        )(),
        scopes=["*"],
        skill=skill,
    )

    assert context.allowed_tools == ["workspace.read_file"]

