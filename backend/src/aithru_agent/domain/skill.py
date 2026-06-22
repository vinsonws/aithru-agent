from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from .base import AithruBaseModel


class AgentSkillStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class AgentWorkspacePolicy(AithruBaseModel):
    read: bool = True
    write: bool = False
    allowed_paths: list[str] | None = None
    max_file_size_bytes: int | None = None


class AgentMemoryPolicy(AithruBaseModel):
    read: bool = False
    write: bool = False
    scopes: list[str] | None = None


class AgentSandboxMount(AithruBaseModel):
    source: str
    target: str
    mode: Literal["read", "write"] = "read"

    @field_validator("source", "target")
    @classmethod
    def _path_must_be_absolute(cls, value: str) -> str:
        path = value.strip()
        if not path.startswith("/"):
            raise ValueError("sandbox mount paths must be absolute")
        return path


class AgentSandboxPolicy(AithruBaseModel):
    enabled: bool = False
    network: Literal["none", "allowlist", "full"] = "none"
    allowed_commands: list[str] | None = None
    allowed_packages: list[str] | None = None
    allowed_mounts: list[AgentSandboxMount] | None = None
    timeout_ms: int | None = Field(default=None, ge=1, le=5_000)

    @field_validator("allowed_commands", "allowed_packages")
    @classmethod
    def _list_items_must_not_be_blank(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        stripped = [item.strip() for item in value]
        if any(not item for item in stripped):
            raise ValueError("sandbox policy lists cannot contain blank items")
        return stripped


class AgentApprovalPolicy(AithruBaseModel):
    default_decision: str = "require_approval"
    require_approval_for_risk: list[str] = []


class AgentSkill(AithruBaseModel):
    id: str
    org_id: str
    key: str
    name: str
    description: str | None = None
    instructions: str
    when_to_use: str | None = None
    enabled: bool = True
    allowed_tools: list[str]
    denied_tools: list[str] = []
    allowed_subagents: list[str]
    workspace_policy: AgentWorkspacePolicy | None = None
    memory_policy: AgentMemoryPolicy | None = None
    sandbox_policy: AgentSandboxPolicy | None = None
    approval_policy: AgentApprovalPolicy | None = None
    input_schema: object | None = None
    output_schema: object | None = None
    version: str
    status: AgentSkillStatus
