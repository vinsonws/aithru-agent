from enum import StrEnum
from typing import Any

from pydantic import Field

from aithru_agent.domain.base import AithruBaseModel


class AgentStreamVisibility(StrEnum):
    USER = "user"
    DEBUG = "debug"
    AUDIT = "audit"


class AgentStreamRedaction(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


class AgentStreamSource(AithruBaseModel):
    kind: str
    id: str | None = None
    name: str | None = None


class AgentStreamEvent(AithruBaseModel):
    id: str
    run_id: str
    thread_id: str | None = None
    sequence: int
    timestamp: str
    type: str
    source: AgentStreamSource
    visibility: AgentStreamVisibility = AgentStreamVisibility.USER
    redaction: AgentStreamRedaction = AgentStreamRedaction.NONE
    summary: str | None = None
    payload: Any = Field(default_factory=dict)

