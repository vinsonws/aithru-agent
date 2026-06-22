"""Parser for harness-native progressive skill files."""

from dataclasses import dataclass
from typing import Any

import yaml


@dataclass(frozen=True)
class ProgressiveSkill:
    """A context/tool/policy package loaded progressively by the agent runtime."""

    name: str
    description: str
    instructions: str
    tags: list[str] | None = None
    when_to_use: str | None = None
    when_to_use_summary: str | None = None
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    workspace_allowed_paths: list[str] | None = None
    workspace_readonly: bool = False
    memory_read_scopes: list[str] | None = None
    memory_write_scopes: list[str] | None = None
    sandbox_enabled: bool = False
    sandbox_allowed_commands: list[str] | None = None
    sandbox_allowed_packages: list[str] | None = None
    sandbox_mounts: list[dict[str, str]] | None = None
    sandbox_network: str | None = None
    sandbox_timeout_ms: int | None = None
    requires_approval_for_risk: list[str] | None = None
    metadata: dict[str, Any] | None = None


def parse_skill_md(content: str) -> ProgressiveSkill:
    """Parse a SKILL.md file with YAML frontmatter and policy sections."""
    frontmatter: dict[str, Any] = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            loaded = yaml.safe_load(parts[1]) or {}
            if isinstance(loaded, dict):
                frontmatter = loaded
            body = parts[2]

    name = str(frontmatter.get("name") or "unnamed-skill")
    description = str(frontmatter.get("description") or "")
    tags = _string_list(frontmatter.get("tags"))

    when_to_use = _section(body, "Activation")
    when_to_use_summary = when_to_use.splitlines()[0] if when_to_use else None
    tool_policy = _section(body, "Tool Policy")
    workspace_policy = _section(body, "Workspace Policy")
    memory_policy = _section(body, "Memory Policy")
    sandbox_policy = _section(body, "Sandbox Policy")
    approval_policy = _section(body, "Approval Policy")

    return ProgressiveSkill(
        name=name,
        description=description,
        instructions=body.strip(),
        tags=tags,
        when_to_use=when_to_use,
        when_to_use_summary=when_to_use_summary,
        allowed_tools=_policy_list(tool_policy, "Allowed"),
        denied_tools=_policy_list(tool_policy, "Denied"),
        workspace_allowed_paths=_policy_list(workspace_policy, "Paths"),
        workspace_readonly=_policy_bool(workspace_policy, "Readonly"),
        memory_read_scopes=_policy_list(memory_policy, "Read"),
        memory_write_scopes=_policy_list(memory_policy, "Write"),
        sandbox_enabled=_policy_bool(sandbox_policy, "Enabled"),
        sandbox_allowed_commands=_policy_list(sandbox_policy, "Allowed Commands"),
        sandbox_allowed_packages=_policy_list(sandbox_policy, "Allowed Packages"),
        sandbox_mounts=_policy_mounts(sandbox_policy, "Mounts"),
        sandbox_network=_policy_value(sandbox_policy, "Network"),
        sandbox_timeout_ms=_policy_int(sandbox_policy, "Timeout"),
        requires_approval_for_risk=_policy_list(approval_policy, "Require Approval"),
        metadata=frontmatter,
    )


def _section(body: str, title: str) -> str | None:
    marker = f"## {title}"
    if marker not in body:
        return None
    section = body.split(marker, 1)[1]
    if "\n## " in section:
        section = section.split("\n## ", 1)[0]
    section = section.strip()
    return section or None


def _policy_list(section: str | None, key: str) -> list[str] | None:
    if not section:
        return None
    prefix = f"{key}:"
    for line in section.splitlines():
        if line.strip().startswith(prefix):
            return [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
    return None


def _policy_bool(section: str | None, key: str) -> bool:
    if not section:
        return False
    prefix = f"{key}:"
    for line in section.splitlines():
        if line.strip().startswith(prefix):
            return line.split(":", 1)[1].strip().lower() == "true"
    return False


def _policy_value(section: str | None, key: str) -> str | None:
    if not section:
        return None
    prefix = f"{key}:"
    for line in section.splitlines():
        if line.strip().startswith(prefix):
            value = line.split(":", 1)[1].strip()
            return value or None
    return None


def _policy_int(section: str | None, key: str) -> int | None:
    value = _policy_value(section, key)
    return int(value) if value is not None else None


def _policy_mounts(section: str | None, key: str) -> list[dict[str, str]] | None:
    value = _policy_value(section, key)
    if value is None:
        return None
    mounts = []
    for item in value.split(","):
        raw = item.strip()
        if not raw:
            continue
        source, target_and_mode = [part.strip() for part in raw.split("->", 1)]
        if ":" in target_and_mode:
            target, mode = [part.strip() for part in target_and_mode.rsplit(":", 1)]
        else:
            target, mode = target_and_mode, "read"
        mounts.append({"source": source, "target": target, "mode": mode})
    return mounts or None


def _string_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
