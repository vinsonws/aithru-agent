from enum import StrEnum
from typing import Literal

from .base import AithruBaseModel


class AgentTodoStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


AgentTodoCreatorType = Literal["agent", "user", "system"]


class AgentTodo(AithruBaseModel):
    id: str
    run_id: str
    title: str
    description: str | None = None
    status: AgentTodoStatus
    created_by: AgentTodoCreatorType
    order: int

