import json
from pathlib import Path

from aithru_agent.domain import AgentSkill, AgentSkillStatus


class FileSkillLoader:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        for manifest in self._root.glob("*/skill.json"):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("id") != skill_id_or_key and data.get("key") != skill_id_or_key:
                continue
            skill = AgentSkill.model_validate(data)
            if skill.status != AgentSkillStatus.PUBLISHED:
                return None
            return skill
        return None

