from pathlib import Path

from aithru_agent.skills.loader import FileSkillLoader


def test_file_skill_loader_loads_published_skill_manifest(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "file-report"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.json").write_text(
        """
        {
          "id": "skill_1",
          "org_id": "org_1",
          "key": "file-report",
          "name": "File Report",
          "instructions": "Analyze files and write a concise report.",
          "allowed_tools": ["workspace.read_file", "artifact.create"],
          "allowed_subagents": [],
          "version": "0.1.0",
          "status": "published"
        }
        """,
        encoding="utf-8",
    )

    loader = FileSkillLoader(skill_dir.parent)

    skill = loader.resolve("file-report")

    assert skill is not None
    assert skill.id == "skill_1"
    assert skill.instructions == "Analyze files and write a concise report."
    assert skill.allowed_tools == ["workspace.read_file", "artifact.create"]


def test_file_skill_loader_returns_none_for_missing_or_unpublished_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "draft"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.json").write_text(
        """
        {
          "id": "skill_draft",
          "org_id": "org_1",
          "key": "draft",
          "name": "Draft",
          "instructions": "Draft only.",
          "allowed_tools": [],
          "allowed_subagents": [],
          "version": "0.1.0",
          "status": "draft"
        }
        """,
        encoding="utf-8",
    )

    loader = FileSkillLoader(skill_dir.parent)

    assert loader.resolve("draft") is None
    assert loader.resolve("missing") is None
