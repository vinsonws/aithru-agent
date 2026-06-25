"""Skill package domain: metadata, parsing, and rendering."""

from datetime import UTC, datetime
from typing import Any

import yaml

from aithru_agent.domain import (
    AgentSkill,
    AgentSkillConfiguration,
    AgentSkillRegistrySource,
    AgentSkillStatus,
)
from aithru_agent.domain.base import AithruBaseModel


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class SkillPackageMetadata(AithruBaseModel):
    name: str
    description: str


class SkillPackage(AithruBaseModel):
    id: str
    org_id: str
    key: str
    source: AgentSkillRegistrySource
    owner_user_id: str | None = None
    skill_md: str
    metadata: SkillPackageMetadata
    instructions: str
    policy: AgentSkillConfiguration
    version: str = "0.1.0"
    status: AgentSkillStatus = AgentSkillStatus.PUBLISHED
    enabled: bool = True
    read_only: bool = False
    created_at: str
    updated_at: str

    @property
    def discovery_description(self) -> str:
        return f"{self.metadata.name}: {self.metadata.description}"

    def to_skill(self) -> AgentSkill:
        return skill_package_to_agent_skill(self)


def parse_skill_md_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from SKILL.md content."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    loaded = yaml.safe_load(parts[1]) or {}
    if not isinstance(loaded, dict):
        return {}, content
    return loaded, parts[2]


def parse_skill_package(
    *,
    key: str,
    org_id: str,
    owner_user_id: str | None,
    source: AgentSkillRegistrySource,
    skill_md: str,
    policy: AgentSkillConfiguration,
    id: str | None = None,
    version: str = "0.1.0",
    status: AgentSkillStatus = AgentSkillStatus.PUBLISHED,
    enabled: bool = True,
    read_only: bool = False,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> SkillPackage:
    frontmatter, body = parse_skill_md_frontmatter(skill_md)
    name = str(frontmatter.get("name", "unnamed-skill"))
    description = str(frontmatter.get("description", ""))
    metadata = SkillPackageMetadata(name=name, description=description)
    instructions = body.strip()
    now = _utc_now()
    return SkillPackage(
        id=id or f"skill_{key.replace('-', '_')}",
        org_id=org_id,
        key=key,
        source=source,
        owner_user_id=owner_user_id,
        skill_md=skill_md,
        metadata=metadata,
        instructions=instructions,
        policy=policy.model_copy(update={"instructions": instructions}),
        version=version,
        status=status,
        enabled=enabled,
        read_only=read_only,
        created_at=created_at or now,
        updated_at=updated_at or now,
    )


def render_skill_md(
    *,
    name: str,
    description: str,
    body: str,
) -> str:
    """Render a complete SKILL.md string from metadata and body."""
    frontmatter = {"name": name, "description": description}
    parts = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()
    return f"---\n{parts}\n---\n\n{body}"


def skill_package_to_agent_skill(package: SkillPackage) -> AgentSkill:
    return AgentSkill(
        id=package.id,
        org_id=package.org_id,
        key=package.key,
        name=package.metadata.name,
        description=package.metadata.description,
        instructions=package.instructions,
        when_to_use=package.policy.when_to_use,
        enabled=package.enabled,
        allowed_tools=package.policy.allowed_tools,
        denied_tools=package.policy.denied_tools,
        allowed_subagents=package.policy.allowed_subagents,
        workspace_policy=package.policy.workspace_policy,
        memory_policy=package.policy.memory_policy,
        sandbox_policy=package.policy.sandbox_policy,
        approval_policy=package.policy.approval_policy,
        input_schema=package.policy.input_schema,
        output_schema=package.policy.output_schema,
        version=package.version,
        status=package.status,
    )
