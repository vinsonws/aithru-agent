from aithru_agent.domain import (
    AgentSkill,
    AgentSkillStatus,
    AgentWorkspacePolicy,
)


DEEP_RESEARCH_SKILL_KEY = "deep-research"


class BuiltInResearchSkillResolver:
    def __init__(self) -> None:
        self._skills = [_deep_research_skill()]
        self._by_id = {skill.id: skill for skill in self._skills}
        self._by_key = {skill.key: skill for skill in self._skills}

    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        return self._by_id.get(skill_id_or_key) or self._by_key.get(skill_id_or_key)

    def resolve_for_org(self, org_id: str, skill_id_or_key: str) -> AgentSkill | None:
        skill = self.resolve(skill_id_or_key)
        if skill is None or skill.org_id != org_id:
            return None
        return skill

    def list_skills(self) -> list[AgentSkill]:
        return list(self._skills)


def _deep_research_skill() -> AgentSkill:
    return AgentSkill(
        id="skill_deep_research",
        org_id="org_1",
        key=DEEP_RESEARCH_SKILL_KEY,
        name="Deep Research",
        description="Plan research, use controlled web tools, and produce cited report artifacts.",
        instructions=(
            "Use this skill for evidence-backed research tasks. "
            "Start with research.create_plan to create runtime todos and typed research sections. "
            "Use web.search only when it is available in the current tool catalog. "
            "Use web.fetch only for allowed sources that need more evidence. "
            "Finish with research.create_report using structured sources and citations. "
            "Do not create or persist workflow definitions."
        ),
        when_to_use="research, deep research, evidence-backed report, cited web investigation",
        allowed_tools=[
            "research.create_plan",
            "web.search",
            "web.fetch",
            "research.create_report",
            "artifact.create",
            "artifact.finalize",
        ],
        denied_tools=[],
        allowed_subagents=[],
        workspace_policy=AgentWorkspacePolicy(
            read=True,
            write=True,
            allowed_paths=["/reports", "/workspace", "/artifacts"],
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "objective": {"type": "string"},
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "artifact_ids": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
            },
        },
        version="0.1.0",
        status=AgentSkillStatus.PUBLISHED,
    )
