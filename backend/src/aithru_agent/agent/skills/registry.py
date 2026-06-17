"""Progressive skill registry."""

from dataclasses import dataclass, field
from pathlib import Path

from aithru_agent.agent.skills.parser import ProgressiveSkill, parse_skill_md


@dataclass
class SkillRegistry:
    """Loads and indexes progressive skills."""

    skill_dirs: list[Path] = field(default_factory=list)
    _loaded_skills: dict[str, ProgressiveSkill] = field(default_factory=dict)
    _skill_by_tag: dict[str, list[str]] = field(default_factory=dict)

    def add_skill_dir(self, path: Path | str) -> None:
        self.skill_dirs.append(Path(path))

    def register_skill(self, name: str, skill: ProgressiveSkill) -> None:
        self._loaded_skills[name] = skill
        self._loaded_skills.setdefault(skill.name, skill)
        for tag in skill.tags or []:
            self._skill_by_tag.setdefault(tag, []).append(name)

    def load_skill_from_content(self, name: str, content: str) -> ProgressiveSkill:
        skill = parse_skill_md(content)
        self.register_skill(name, skill)
        return skill

    def load_from_dirs(self) -> int:
        count = 0
        for skill_dir in self.skill_dirs:
            if not skill_dir.exists():
                continue
            for skill_file in skill_dir.rglob("SKILL.md"):
                skill_name = skill_file.parent.name
                self.load_skill_from_content(skill_name, skill_file.read_text())
                count += 1
        return count

    def get_skill(self, name: str) -> ProgressiveSkill | None:
        return self._loaded_skills.get(name)

    def find_by_tag(self, tag: str) -> list[ProgressiveSkill]:
        skill_names = self._skill_by_tag.get(tag, [])
        return [self._loaded_skills[name] for name in skill_names if name in self._loaded_skills]

    def list_skills(self) -> list[str]:
        return list(self._loaded_skills.keys())
