"""Progressive skill activation and prompt injection."""

import re
from dataclasses import dataclass

from aithru_agent.agent.skills.parser import ProgressiveSkill
from aithru_agent.agent.skills.registry import SkillRegistry


@dataclass(frozen=True)
class ActivationMatch:
    skill_name: str
    confidence: float
    matched_trigger: str


class SkillActivator:
    """Detects progressive skills relevant to a run goal."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def detect_skills_for_goal(
        self,
        goal: str,
        skill_id_hint: str | None = None,
    ) -> list[ActivationMatch]:
        matches: list[ActivationMatch] = []
        if skill_id_hint and self._registry.get_skill(skill_id_hint):
            return [
                ActivationMatch(
                    skill_name=skill_id_hint,
                    confidence=1.0,
                    matched_trigger="explicit_skill_id",
                )
            ]

        for skill_name in self._registry.list_skills():
            skill = self._registry.get_skill(skill_name)
            if skill is None:
                continue
            confidence = self._match_skill(skill, goal)
            if confidence > 0.3:
                matches.append(
                    ActivationMatch(
                        skill_name=skill_name,
                        confidence=confidence,
                        matched_trigger="heuristic_match",
                    )
                )

        matches.sort(key=lambda match: -match.confidence)
        return matches

    def inject_skill_context(self, instructions: str, skills: list[ProgressiveSkill]) -> str:
        if not skills:
            return instructions

        sections = ["\n\n## Activated Skills"]
        for skill in skills:
            sections.append(f"### {skill.name}: {skill.description}")
            if skill.when_to_use_summary:
                sections.append(f"Purpose: {skill.when_to_use_summary}")
            sections.append(skill.instructions)
            if skill.allowed_tools:
                sections.append(f"Allowed tools: {', '.join(skill.allowed_tools)}")

        return instructions + "\n".join(sections)

    def _match_skill(self, skill: ProgressiveSkill, goal: str) -> float:
        confidence = 0.0
        goal_lower = goal.lower()
        for word in skill.name.lower().replace("-", " ").replace("_", " ").split():
            if len(word) > 3 and word in goal_lower:
                confidence += 0.1
        if skill.description:
            for word in re.findall(r"\w+", skill.description.lower()):
                if len(word) > 4 and word in goal_lower:
                    confidence += 0.05
        if skill.when_to_use_summary:
            for word in re.findall(r"\w+", skill.when_to_use_summary.lower()):
                if len(word) > 3 and word in goal_lower:
                    confidence += 0.15
        return min(confidence, 0.95)
