from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator

from .base import AithruBaseModel
from .tool import AgentToolRiskLevel


class AgentSkillStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class AgentSkillRegistrySource(StrEnum):
    BUILTIN = "builtin"
    MANAGED = "managed"
    MARKETPLACE = "marketplace"
    USER = "user"


class AgentWorkspacePolicy(AithruBaseModel):
    read: bool = True
    write: bool = False
    allowed_paths: list[str] | None = None
    max_file_size_bytes: int | None = None


class AgentMemoryPolicy(AithruBaseModel):
    read: bool = False
    write: bool = False
    scopes: list[Literal["user", "thread", "workspace", "organization", "skill"]] | None = None


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
    default_decision: Literal["require_approval"] = "require_approval"
    require_approval_for_risk: list[AgentToolRiskLevel] = Field(default_factory=list)

    @field_validator("require_approval_for_risk", mode="before")
    @classmethod
    def _risk_levels_must_not_be_blank(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        stripped = [item.strip() if isinstance(item, str) else item for item in value]
        if any(not item for item in stripped):
            raise ValueError("approval policy risk entries cannot be blank")
        return stripped


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


class AgentSkillMarketplaceMetadata(AithruBaseModel):
    listing_id: str | None = None
    publisher: str | None = None
    homepage_url: str | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AgentSkillConfiguration(AithruBaseModel):
    instructions: str
    when_to_use: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    allowed_subagents: list[str] = Field(default_factory=list)
    workspace_policy: AgentWorkspacePolicy | None = None
    memory_policy: AgentMemoryPolicy | None = None
    sandbox_policy: AgentSandboxPolicy | None = None
    approval_policy: AgentApprovalPolicy | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    @classmethod
    def from_skill(cls, skill: AgentSkill) -> "AgentSkillConfiguration":
        return cls(
            instructions=skill.instructions,
            when_to_use=skill.when_to_use,
            allowed_tools=skill.allowed_tools,
            denied_tools=skill.denied_tools,
            allowed_subagents=skill.allowed_subagents,
            workspace_policy=skill.workspace_policy,
            memory_policy=skill.memory_policy,
            sandbox_policy=skill.sandbox_policy,
            approval_policy=skill.approval_policy,
            input_schema=skill.input_schema if isinstance(skill.input_schema, dict) else None,
            output_schema=skill.output_schema if isinstance(skill.output_schema, dict) else None,
        )


class AgentSkillRegistryEntry(AithruBaseModel):
    id: str
    org_id: str
    key: str
    name: str
    description: str | None = None
    version: str
    status: AgentSkillStatus
    enabled: bool = True
    source: AgentSkillRegistrySource = AgentSkillRegistrySource.MANAGED
    owner_user_id: str | None = None
    marketplace: AgentSkillMarketplaceMetadata | None = None
    configuration: AgentSkillConfiguration
    read_only: bool = False
    created_at: str
    updated_at: str

    @classmethod
    def from_skill(
        cls,
        skill: AgentSkill,
        *,
        source: AgentSkillRegistrySource,
        created_at: str,
        updated_at: str | None = None,
        marketplace: AgentSkillMarketplaceMetadata | None = None,
        read_only: bool = False,
        owner_user_id: str | None = None,
    ) -> "AgentSkillRegistryEntry":
        return cls(
            id=skill.id,
            org_id=skill.org_id,
            key=skill.key,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            status=skill.status,
            enabled=skill.enabled,
            source=source,
            owner_user_id=owner_user_id,
            marketplace=marketplace,
            configuration=AgentSkillConfiguration.from_skill(skill),
            read_only=read_only,
            created_at=created_at,
            updated_at=updated_at or created_at,
        )

    @classmethod
    def from_package(
        cls,
        package: object,
    ) -> "AgentSkillRegistryEntry":
        from aithru_agent.skills.packages import SkillPackage

        if not isinstance(package, SkillPackage):
            raise TypeError(f"Expected SkillPackage, got {type(package)}")
        return cls(
            id=package.id,
            org_id=package.org_id,
            key=package.key,
            name=package.metadata.name,
            description=package.metadata.description,
            version=package.version,
            status=package.status,
            enabled=package.enabled,
            source=package.source,
            owner_user_id=package.owner_user_id,
            configuration=package.policy,
            read_only=package.read_only,
            created_at=package.created_at,
            updated_at=package.updated_at,
        )

    def to_skill(self) -> AgentSkill:
        return AgentSkill(
            id=self.id,
            org_id=self.org_id,
            key=self.key,
            name=self.name,
            description=self.description,
            instructions=self.configuration.instructions,
            when_to_use=self.configuration.when_to_use,
            enabled=self.enabled,
            allowed_tools=self.configuration.allowed_tools,
            denied_tools=self.configuration.denied_tools,
            allowed_subagents=self.configuration.allowed_subagents,
            workspace_policy=self.configuration.workspace_policy,
            memory_policy=self.configuration.memory_policy,
            sandbox_policy=self.configuration.sandbox_policy,
            approval_policy=self.configuration.approval_policy,
            input_schema=self.configuration.input_schema,
            output_schema=self.configuration.output_schema,
            version=self.version,
            status=self.status,
        )


class AgentSkillEnablementResult(AithruBaseModel):
    id: str
    org_id: str
    key: str
    enabled: bool
    status: AgentSkillStatus
    runtime_visible: bool
    entry: AgentSkillRegistryEntry
