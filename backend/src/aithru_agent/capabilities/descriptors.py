from typing import Literal

from pydantic import BaseModel, Field, field_validator

from aithru_agent.domain import (
    AgentActorContext,
    AgentAuthorizationDecision,
    AgentCapabilityAuditEvent,
    AgentSandboxPolicy,
)
from aithru_agent.domain.actor import normalize_scope_list


class AgentRunContext(BaseModel):
    run_id: str
    org_id: str
    actor_user_id: str
    workspace_id: str
    thread_id: str | None = None
    skill_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    actor_context: AgentActorContext | None = None
    allowed_tools: list[str] | None = None
    denied_tools: list[str] = Field(default_factory=list)
    allowed_subagents: list[str] | None = None
    workspace_allowed_paths: list[str] | None = None
    sandbox_policy: AgentSandboxPolicy | None = None
    require_approval_for_risk: list[str] = Field(default_factory=list)
    model_vision_enabled: bool = False

    @field_validator("scopes")
    @classmethod
    def _scopes_must_be_normalized(cls, value: list[str]) -> list[str]:
        return normalize_scope_list(value)

    def actor(self) -> AgentActorContext:
        if self.actor_context is not None:
            return self.actor_context.model_copy(update={"scopes": self.scopes})
        return AgentActorContext(
            actor_type="user",
            org_id=self.org_id,
            user_id=self.actor_user_id,
            scopes=self.scopes,
        )

    def authorize_scopes(
        self,
        required_scopes: list[str],
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> AgentAuthorizationDecision:
        return AgentAuthorizationDecision.from_scope_check(
            actor=self.actor(),
            required_scopes=required_scopes,
            granted_scopes=self.scopes,
            resource_type=resource_type,
            resource_id=resource_id,
        )


class ToolPolicy(BaseModel):
    require_approval_for_risk: list[str] = Field(default_factory=list)


class AgentToolPrepareResult(BaseModel):
    status: Literal["ready", "denied", "waiting_approval"]
    tool_name: str
    reason: str | None = None
    output: object | None = None
    authorization: AgentAuthorizationDecision | None = None
    audit: AgentCapabilityAuditEvent | None = None
