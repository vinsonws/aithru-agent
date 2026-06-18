from typing import Protocol

from aithru_agent.domain import AgentSkill, AgentSkillStatus


class AgentSkillResolver(Protocol):
    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        ...

    def list_skills(self) -> list[AgentSkill]:
        ...


class EmptySkillResolver:
    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        del skill_id_or_key
        return None

    def list_skills(self) -> list[AgentSkill]:
        return []


class InMemorySkillResolver:
    def __init__(self, skills: list[AgentSkill]) -> None:
        active_skills = [skill for skill in skills if _is_active(skill)]
        self._by_id = {skill.id: skill for skill in active_skills}
        self._by_key = {skill.key: skill for skill in active_skills}

    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        return self._by_id.get(skill_id_or_key) or self._by_key.get(skill_id_or_key)

    def list_skills(self) -> list[AgentSkill]:
        return list(self._by_id.values())


def _is_active(skill: AgentSkill) -> bool:
    return skill.status == AgentSkillStatus.PUBLISHED and skill.enabled
