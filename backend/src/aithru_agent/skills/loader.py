import json
from pathlib import Path

from aithru_agent.domain import AgentSkill, AgentSkillStatus


class FileSkillLoader:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        for skill in self.list_skills():
            if skill.id == skill_id_or_key or skill.key == skill_id_or_key:
                return skill
        return None

    def list_skills(self) -> list[AgentSkill]:
        skills: list[AgentSkill] = []
        for manifest in self._root.glob("*/skill.json"):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            skill = AgentSkill.model_validate(data)
            if skill.status == AgentSkillStatus.PUBLISHED:
                skills.append(skill)
        return skills
