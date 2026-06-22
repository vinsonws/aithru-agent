from aithru_agent.domain import AgentWorkspacePolicy
from aithru_agent.skills import BuiltInResearchSkillResolver


def test_builtin_research_skill_is_pydantic_validated_package() -> None:
    resolver = BuiltInResearchSkillResolver()

    skill = resolver.resolve("deep-research")

    assert skill is not None
    assert skill.id == "skill_deep_research"
    assert skill.key == "deep-research"
    assert skill.name == "Deep Research"
    assert skill.status == "published"
    assert skill.allowed_tools == [
        "research.create_plan",
        "web.search",
        "web.fetch",
        "research.create_report",
        "artifact.create",
        "artifact.finalize",
    ]
    assert isinstance(skill.workspace_policy, AgentWorkspacePolicy)
    assert skill.workspace_policy.read is True
    assert skill.workspace_policy.write is True
    assert skill.workspace_policy.allowed_paths == ["/reports", "/workspace", "/artifacts"]
    assert "research.create_plan" in skill.instructions
    assert resolver.resolve("skill_deep_research") == skill
    assert resolver.list_skills() == [skill]
