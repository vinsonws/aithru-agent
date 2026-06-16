from typing import Protocol

from aithru_agent.domain import AgentSkill, AgentSkillStatus


class AgentSkillResolver(Protocol):
    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        ...


class EmptySkillResolver:
    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        del skill_id_or_key
        return None


class InMemorySkillResolver:
    def __init__(self, skills: list[AgentSkill]) -> None:
        self._by_id = {skill.id: skill for skill in skills if skill.status == AgentSkillStatus.PUBLISHED}
        self._by_key = {skill.key: skill for skill in skills if skill.status == AgentSkillStatus.PUBLISHED}

    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        return self._by_id.get(skill_id_or_key) or self._by_key.get(skill_id_or_key)

