from enum import StrEnum

from .base import AithruBaseModel


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRunSource(StrEnum):
    CHAT = "chat"
    SKILL = "skill"
    API = "api"
    WORKBENCH_NODE = "workbench_node"
    DELEGATED_TASK = "delegated_task"


class AgentRun(AithruBaseModel):
    id: str
    org_id: str
    actor_user_id: str
    source: AgentRunSource
    thread_id: str | None = None
    skill_id: str | None = None
    workspace_id: str
    goal: str
    status: AgentRunStatus
    started_at: str
    completed_at: str | None = None
    current_approval_id: str | None = None
    error: dict | None = None

