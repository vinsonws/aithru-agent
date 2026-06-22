from aithru_agent.domain import AgentSkill
from aithru_agent.skills import SQLiteSkillRegistry


def test_sqlite_skill_registry_reconciles_read_only_seed_entries(tmp_path) -> None:
    db_path = tmp_path / "agent.sqlite"
    SQLiteSkillRegistry(
        db_path,
        seed_skills=[
            AgentSkill(
                id="skill_deep_research",
                org_id="org_1",
                key="deep-research",
                name="Deep Research",
                instructions="Instructions A.",
                allowed_tools=["research.create_plan"],
                allowed_subagents=[],
                version="0.1.0",
                status="published",
            )
        ],
    )

    reloaded = SQLiteSkillRegistry(
        db_path,
        seed_skills=[
            AgentSkill(
                id="skill_deep_research",
                org_id="org_1",
                key="deep-research",
                name="Deep Research",
                instructions="Instructions B.",
                allowed_tools=["research.create_plan", "research.create_report"],
                allowed_subagents=[],
                version="0.2.0",
                status="published",
            )
        ],
    )

    entry = reloaded.get_entry("org_1", "deep-research")
    assert entry is not None
    assert entry.read_only is True
    assert entry.version == "0.2.0"
    assert entry.configuration.instructions == "Instructions B."
    assert entry.configuration.allowed_tools == ["research.create_plan", "research.create_report"]


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
