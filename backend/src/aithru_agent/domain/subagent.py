from enum import StrEnum

from .base import AithruBaseModel
from .skill import AgentMemoryPolicy, AgentWorkspacePolicy


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
    error: dict | None = None
    created_at: str
    completed_at: str | None = None
