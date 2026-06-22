from typing import Protocol

from aithru_agent.domain import AgentSkill, AgentSkillStatus


class AgentSkillResolver(Protocol):
    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        ...

    def resolve_for_org(self, org_id: str, skill_id_or_key: str) -> AgentSkill | None:
        ...

    def list_skills(self) -> list[AgentSkill]:
        ...


class EmptySkillResolver:
    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        del skill_id_or_key
        return None

    def resolve_for_org(self, org_id: str, skill_id_or_key: str) -> AgentSkill | None:
        del org_id, skill_id_or_key
        return None

    def list_skills(self) -> list[AgentSkill]:
        return []


class InMemorySkillResolver:
    def __init__(self, skills: list[AgentSkill]) -> None:
        active_skills = [skill for skill in skills if _is_active(skill)]
        self._skills = active_skills
        self._by_id = {skill.id: skill for skill in active_skills}
        self._by_key = {skill.key: skill for skill in active_skills}

    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        return self._by_id.get(skill_id_or_key) or self._by_key.get(skill_id_or_key)

    def resolve_for_org(self, org_id: str, skill_id_or_key: str) -> AgentSkill | None:
        for skill in self._skills:
            if skill.org_id == org_id and skill_id_or_key in {skill.id, skill.key}:
                return skill
        return None

    def list_skills(self) -> list[AgentSkill]:
        return list(self._by_id.values())


def resolve_skill_for_org(
    resolver: AgentSkillResolver,
    org_id: str,
    skill_id_or_key: str,
) -> AgentSkill | None:
    resolve_for_org = getattr(resolver, "resolve_for_org", None)
    if callable(resolve_for_org):
        return resolve_for_org(org_id, skill_id_or_key)
    skill = resolver.resolve(skill_id_or_key)
    if skill is None or skill.org_id != org_id:
        return None
    return skill


def _is_active(skill: AgentSkill) -> bool:
    return skill.status == AgentSkillStatus.PUBLISHED and skill.enabled
