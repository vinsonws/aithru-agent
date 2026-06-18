import json
from pathlib import Path
from typing import Any

from aithru_agent.agent.skills import ProgressiveSkill, parse_skill_md
from aithru_agent.domain import (
    AgentApprovalPolicy,
    AgentMemoryPolicy,
    AgentSandboxPolicy,
    AgentSkill,
    AgentSkillStatus,
    AgentWorkspacePolicy,
)


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
        seen_paths: set[Path] = set()
        for manifest in self._root.rglob("skill.json"):
            seen_paths.add(manifest.parent)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            skill = AgentSkill.model_validate(data)
            if _is_active(skill):
                skills.append(skill)
        for skill_file in self._root.rglob("SKILL.md"):
            if skill_file.parent in seen_paths:
                continue
            skill = _skill_from_package(skill_file)
            if _is_active(skill):
                skills.append(skill)
        return skills


def _skill_from_package(skill_file: Path) -> AgentSkill:
    parsed = parse_skill_md(skill_file.read_text(encoding="utf-8"))
    metadata = parsed.metadata or {}
    key = _metadata_str(metadata, "key") or skill_file.parent.name
    return AgentSkill(
        id=_metadata_str(metadata, "id") or f"skill_{key.replace('-', '_')}",
        org_id=_metadata_str(metadata, "org_id") or "org_1",
        key=key,
        name=_metadata_str(metadata, "name") or parsed.name,
        description=_metadata_str(metadata, "description") or parsed.description or None,
        instructions=parsed.instructions,
        when_to_use=_metadata_str(metadata, "when_to_use") or parsed.when_to_use_summary,
        enabled=_metadata_bool(metadata, "enabled", default=True),
        allowed_tools=_metadata_list(metadata, "allowed_tools") or parsed.allowed_tools or [],
        denied_tools=_metadata_list(metadata, "denied_tools") or parsed.denied_tools or [],
        allowed_subagents=_metadata_list(metadata, "allowed_subagents") or [],
        workspace_policy=_workspace_policy(parsed),
        memory_policy=_memory_policy(parsed),
        sandbox_policy=_sandbox_policy(parsed),
        approval_policy=_approval_policy(parsed),
        version=_metadata_str(metadata, "version") or "0.1.0",
        status=_metadata_status(metadata.get("status")),
    )


def _workspace_policy(skill: ProgressiveSkill) -> AgentWorkspacePolicy | None:
    if not skill.workspace_allowed_paths and not skill.workspace_readonly:
        return None
    return AgentWorkspacePolicy(
        read=True,
        write=not skill.workspace_readonly,
        allowed_paths=skill.workspace_allowed_paths,
    )


def _memory_policy(skill: ProgressiveSkill) -> AgentMemoryPolicy | None:
    read_scopes = skill.memory_read_scopes or []
    write_scopes = skill.memory_write_scopes or []
    if not read_scopes and not write_scopes:
        return None
    return AgentMemoryPolicy(
        read=bool(read_scopes),
        write=bool(write_scopes),
        scopes=[*read_scopes, *[scope for scope in write_scopes if scope not in read_scopes]],
    )


def _sandbox_policy(skill: ProgressiveSkill) -> AgentSandboxPolicy | None:
    if not skill.sandbox_enabled and not skill.sandbox_allowed_commands:
        return None
    return AgentSandboxPolicy(
        enabled=skill.sandbox_enabled,
        allowed_commands=skill.sandbox_allowed_commands,
    )


def _approval_policy(skill: ProgressiveSkill) -> AgentApprovalPolicy | None:
    if not skill.requires_approval_for_risk:
        return None
    return AgentApprovalPolicy(require_approval_for_risk=skill.requires_approval_for_risk)


def _is_active(skill: AgentSkill) -> bool:
    return skill.status == AgentSkillStatus.PUBLISHED and skill.enabled


def _metadata_str(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    return str(value)


def _metadata_bool(metadata: dict[str, Any], key: str, *, default: bool) -> bool:
    value = metadata.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _metadata_list(metadata: dict[str, Any], key: str) -> list[str] | None:
    value = metadata.get(key)
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _metadata_status(value: object) -> AgentSkillStatus:
    if isinstance(value, AgentSkillStatus):
        return value
    if value is None:
        return AgentSkillStatus.PUBLISHED
    return AgentSkillStatus(str(value).strip().lower())
