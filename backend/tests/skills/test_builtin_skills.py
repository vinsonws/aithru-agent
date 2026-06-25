from aithru_agent.domain import AgentWorkspacePolicy
from aithru_agent.skills import BuiltInResearchSkillResolver


def test_builtin_skills_load_all_ten() -> None:
    resolver = BuiltInResearchSkillResolver()

    skills = resolver.list_skills()
    assert len(skills) == 10

    keys = {skill.key for skill in skills}
    assert keys == {
        "deep-research",
        "surprise-me",
        "bootstrap",
        "find-skills",
        "skill-creator",
        "frontend-design",
        "chart-visualization",
        "web-design-guidelines",
        "ppt-generation",
        "data-analysis",
    }

    for skill in skills:
        assert skill.status == "published"
        assert skill.enabled is True
        assert skill.instructions


def test_builtin_deep_research_skill() -> None:
    resolver = BuiltInResearchSkillResolver()

    skill = resolver.resolve("deep-research")
    assert skill is not None
    assert skill.id == "skill_deep_research"
    assert skill.key == "deep-research"
    assert skill.name == "Deep Research"
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
    assert "research.create_plan" in skill.instructions
    assert resolver.resolve("skill_deep_research") == skill


def test_builtin_surprise_me_skill() -> None:
    resolver = BuiltInResearchSkillResolver()
    skill = resolver.resolve("surprise-me")
    assert skill is not None
    assert skill.id == "skill_surprise_me"
    assert skill.key == "surprise-me"
    assert skill.name == "Surprise Me"
    assert "artifact.create" in skill.allowed_tools


def test_builtin_bootstrap_skill() -> None:
    resolver = BuiltInResearchSkillResolver()
    skill = resolver.resolve("bootstrap")
    assert skill is not None
    assert skill.id == "skill_bootstrap"
    assert skill.key == "bootstrap"
    assert skill.name == "Bootstrap"
    assert "workspace.write_file" in skill.allowed_tools


def test_builtin_find_skills_skill() -> None:
    resolver = BuiltInResearchSkillResolver()
    skill = resolver.resolve("find-skills")
    assert skill is not None
    assert skill.id == "skill_find_skills"
    assert skill.key == "find-skills"
    assert skill.name == "Find Skills"


def test_builtin_skill_creator_skill() -> None:
    resolver = BuiltInResearchSkillResolver()
    skill = resolver.resolve("skill-creator")
    assert skill is not None
    assert skill.id == "skill_skill_creator"
    assert skill.key == "skill-creator"
    assert skill.name == "Skill Creator"
    assert "workspace.write_file" in skill.allowed_tools


def test_builtin_frontend_design_skill() -> None:
    resolver = BuiltInResearchSkillResolver()
    skill = resolver.resolve("frontend-design")
    assert skill is not None
    assert skill.id == "skill_frontend_design"
    assert skill.key == "frontend-design"
    assert skill.name == "Frontend Design"
    assert "artifact.create" in skill.allowed_tools


def test_builtin_chart_visualization_skill() -> None:
    resolver = BuiltInResearchSkillResolver()
    skill = resolver.resolve("chart-visualization")
    assert skill is not None
    assert skill.id == "skill_chart_visualization"
    assert skill.key == "chart-visualization"
    assert skill.name == "Chart Visualization"
    assert "artifact.create" in skill.allowed_tools


def test_builtin_web_design_guidelines_skill() -> None:
    resolver = BuiltInResearchSkillResolver()
    skill = resolver.resolve("web-design-guidelines")
    assert skill is not None
    assert skill.id == "skill_web_design_guidelines"
    assert skill.key == "web-design-guidelines"
    assert skill.name == "Web Design Guidelines"
    assert "web.fetch" in skill.allowed_tools


def test_builtin_ppt_generation_skill() -> None:
    resolver = BuiltInResearchSkillResolver()
    skill = resolver.resolve("ppt-generation")
    assert skill is not None
    assert skill.id == "skill_ppt_generation"
    assert skill.key == "ppt-generation"
    assert skill.name == "PPT Generation"
    assert "artifact.create" in skill.allowed_tools


def test_builtin_data_analysis_skill() -> None:
    resolver = BuiltInResearchSkillResolver()
    skill = resolver.resolve("data-analysis")
    assert skill is not None
    assert skill.id == "skill_data_analysis"
    assert skill.key == "data-analysis"
    assert skill.name == "Data Analysis"
    assert "workspace.read_file" in skill.allowed_tools
