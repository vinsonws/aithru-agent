from typing import Literal

from aithru_agent.domain.base import AithruBaseModel


AgentTraceSpanKind = Literal[
    "run",
    "message",
    "todo",
    "model",
    "tool",
    "approval",
    "subagent",
    "workspace",
    "artifact",
    "external_run",
    "sandbox",
    "memory",
]

AgentTraceSpanStatus = Literal["running", "completed", "failed", "cancelled"]


class AgentTraceSpan(AithruBaseModel):
    id: str
    run_id: str
    kind: AgentTraceSpanKind
    name: str
    status: AgentTraceSpanStatus
    start_sequence: int
    started_at: str
    end_sequence: int | None = None
    ended_at: str | None = None
    refs: dict | None = None
