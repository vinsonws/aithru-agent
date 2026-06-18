"""Skill instruction capability for Pydantic AI capability assembly."""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic_ai.capabilities import AbstractCapability

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.domain import AgentSkill


@dataclass
class SkillInstructionCapability(AbstractCapability[PydanticAgentDeps]):
    """Expose active Aithru skill instructions through the capability path."""

    skills: Sequence[AgentSkill]

    def get_instructions(self) -> str:
        if not self.skills:
            return ""

        sections = ["## Active Aithru Skills"]
        for skill in self.skills:
            sections.append(f"### {skill.name}")
            if skill.description:
                sections.append(skill.description)
            if skill.when_to_use:
                sections.append(f"When to use: {skill.when_to_use}")
            sections.append(skill.instructions)
            if skill.allowed_tools:
                sections.append(f"Allowed tools: {', '.join(skill.allowed_tools)}")
            if skill.denied_tools:
                sections.append(f"Denied tools: {', '.join(skill.denied_tools)}")
        return "\n\n".join(sections)
