from aithru_agent.domain import AgentSkill
from aithru_agent.skills import SQLiteSkillRegistry


def test_sqlite_skill_registry_persists_managed_entries_and_runtime_enablement(tmp_path) -> None:
    db_path = tmp_path / "agent.sqlite"
    registry = SQLiteSkillRegistry(db_path, seed_skills=[])
    registry.register_skill(
        AgentSkill(
            id="skill_file_report",
            org_id="org_1",
            key="file-report",
            name="File Report",
            instructions="Read files and write a report.",
            allowed_tools=["workspace.read_file"],
            allowed_subagents=[],
            version="0.1.0",
            status="published",
            enabled=False,
        )
    )

    reloaded = SQLiteSkillRegistry(db_path, seed_skills=[])
    entry = reloaded.get_entry("org_1", "file-report")
    assert entry is not None
    assert entry.enabled is False
    assert reloaded.resolve("file-report") is None

    reloaded.set_enabled("org_1", "file-report", True)
    enabled_reload = SQLiteSkillRegistry(db_path, seed_skills=[])
    runtime_skill = enabled_reload.resolve("file-report")
    assert runtime_skill is not None
    assert runtime_skill.key == "file-report"
