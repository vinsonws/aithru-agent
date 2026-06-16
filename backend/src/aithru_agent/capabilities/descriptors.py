from typing import Literal

from pydantic import BaseModel


class AgentRunContext(BaseModel):
    run_id: str
    org_id: str
    actor_user_id: str
    workspace_id: str
    thread_id: str | None = None
    skill_id: str | None = None
    scopes: list[str] = []


class ToolPolicy(BaseModel):
    require_approval_for_risk: list[str] = []


class AgentToolPrepareResult(BaseModel):
    status: Literal["ready", "denied", "waiting_approval"]
    tool_name: str
    reason: str | None = None
    output: object | None = None

