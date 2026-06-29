from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel
from .skill import AgentMemoryPolicy, AgentWorkspacePolicy
from .workspace import AgentWorkspaceFile


class AgentSubagentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentSubagentSpec(AithruBaseModel):
    id: str
    org_id: str
    key: str
    name: str
    instructions: str
    allowed_tools: list[str]
    workspace_policy: AgentWorkspacePolicy | None = None
    memory_policy: AgentMemoryPolicy | None = None
    created_at: str
    updated_at: str


class AgentSubagentResultSummary(AithruBaseModel):
    content: str | None = None
    content_truncated: bool = False
    workspace_paths: list[str] = Field(default_factory=list)
    workspace_files: list[AgentWorkspaceFile] = Field(default_factory=list)
    workspace_file_count: int = Field(default=0, ge=0)
    has_output: bool = False
    message_id: str | None = None
    thread_message_id: str | None = None

    @field_validator("workspace_paths")
    @classmethod
    def workspace_paths_must_be_non_blank(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in value:
            stripped = item.strip()
            if not stripped:
                raise ValueError("subagent result workspace paths must not be blank")
            if stripped in seen:
                continue
            seen.add(stripped)
            deduped.append(stripped)
        return deduped

    @model_validator(mode="after")
    def derive_summary_fields(self) -> "AgentSubagentResultSummary":
        if self.content is None and self.content_truncated:
            raise ValueError("content_truncated requires content")
        workspace_paths = list(self.workspace_paths)
        seen = set(workspace_paths)
        for file in self.workspace_files:
            if file.path in seen:
                continue
            seen.add(file.path)
            workspace_paths.append(file.path)
        self.workspace_paths = workspace_paths
        self.workspace_file_count = len(workspace_paths)
        self.has_output = bool((self.content or "").strip() or workspace_paths)
        return self


class AgentSubagentRun(AithruBaseModel):
    id: str
    org_id: str
    parent_run_id: str
    child_run_id: str
    name: str
    task: str
    spec_key: str | None = None
    status: AgentSubagentRunStatus
    result: str | None = None
    result_summary: AgentSubagentResultSummary | None = None
    error: dict | None = None
    created_at: str
    completed_at: str | None = None
