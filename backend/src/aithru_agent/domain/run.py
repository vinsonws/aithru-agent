from enum import StrEnum

from .base import AithruBaseModel


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_SUBAGENT = "waiting_subagent"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRunSource(StrEnum):
    CHAT = "chat"
    SKILL = "skill"
    API = "api"
    WORKBENCH_NODE = "workbench_node"
    DELEGATED_TASK = "delegated_task"


class AgentRunHarnessOptions(AithruBaseModel):
    model: str | None = None
    instructions: str | None = None


class AgentRunResult(AithruBaseModel):
    content: str | None = None
    artifact_ids: list[str] = []
    message_id: str | None = None
    thread_message_id: str | None = None


class AgentRun(AithruBaseModel):
    id: str
    org_id: str
    actor_user_id: str
    source: AgentRunSource
    thread_id: str | None = None
    skill_id: str | None = None
    workspace_id: str
    goal: str
    scopes: list[str] = []
    harness_options: AgentRunHarnessOptions | None = None
    status: AgentRunStatus
    started_at: str
    completed_at: str | None = None
    current_approval_id: str | None = None
    result: AgentRunResult | None = None
    error: dict | None = None
