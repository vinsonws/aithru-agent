from enum import StrEnum

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


class AgentSandboxPolicy(AithruBaseModel):
    enabled: bool = False
    network: str = "none"
    allowed_commands: list[str] | None = None
    timeout_ms: int | None = None


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

