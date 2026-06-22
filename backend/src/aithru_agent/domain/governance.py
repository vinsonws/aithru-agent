from typing import Any, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator

from .actor import AgentActorContext, normalize_scope_list
from .base import AithruBaseModel

AgentScopeGrantSource = Literal["api_token", "run", "skill", "platform", "system"]
AgentAuthorizationStatus = Literal["allowed", "denied"]
AgentCapabilityAuditAction = Literal["tool.prepare", "tool.execute"]
AgentCapabilityAuditOutcome = Literal[
    "allowed",
    "denied",
    "waiting_approval",
    "running",
    "completed",
    "failed",
]
AgentRedactionLevel = Literal["none", "partial", "full"]


class AgentScopeGrant(AithruBaseModel):
    scope: str = Field(min_length=1)
    source: AgentScopeGrantSource = "run"
    resource_type: str | None = None
    resource_id: str | None = None

    @field_validator("scope", "resource_type", "resource_id")
    @classmethod
    def _strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("scope grant strings cannot be blank")
        return stripped

    def covers(self, required_scope: str) -> bool:
        return self.scope == "*" or self.scope == required_scope


class AgentAuthorizationDecision(AithruBaseModel):
    status: AgentAuthorizationStatus
    actor: AgentActorContext
    required_scopes: list[str] = Field(default_factory=list)
    granted_scopes: list[str] = Field(default_factory=list)
    missing_scopes: list[str] = Field(default_factory=list)
    resource_type: str | None = None
    resource_id: str | None = None
    reason: str | None = None

    @field_validator("required_scopes", "granted_scopes", "missing_scopes")
    @classmethod
    def _scope_lists_must_be_normalized(cls, value: list[str]) -> list[str]:
        return normalize_scope_list(value)

    @field_validator("resource_type", "resource_id", "reason")
    @classmethod
    def _optional_strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("authorization strings cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _decision_must_match_missing_scopes(self) -> "AgentAuthorizationDecision":
        if self.status == "allowed" and self.missing_scopes:
            raise ValueError("allowed authorization cannot have missing scopes")
        if self.status == "denied" and not self.missing_scopes:
            raise ValueError("denied authorization requires missing scopes")
        if self.status == "denied" and self.reason is None:
            first_missing = self.missing_scopes[0]
            self.reason = f"Missing required scope: {first_missing}"
        return self

    @classmethod
    def from_scope_check(
        cls,
        *,
        actor: AgentActorContext,
        required_scopes: list[str],
        granted_scopes: list[str],
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> "AgentAuthorizationDecision":
        required = normalize_scope_list(required_scopes)
        granted = normalize_scope_list(granted_scopes)
        missing = [
            scope
            for scope in required
            if scope not in granted and "*" not in granted
        ]
        status: AgentAuthorizationStatus = "denied" if missing else "allowed"
        return cls(
            status=status,
            actor=actor.model_copy(update={"scopes": granted}),
            required_scopes=required,
            granted_scopes=granted,
            missing_scopes=missing,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=f"Missing required scope: {missing[0]}" if missing else None,
        )


class AgentCapabilityAuditEvent(AithruBaseModel):
    action: AgentCapabilityAuditAction
    outcome: AgentCapabilityAuditOutcome
    run_id: str
    tool_name: str
    actor: AgentActorContext
    authorization: AgentAuthorizationDecision = Field(
        validation_alias=AliasChoices("authorization", "authorization_decision"),
        serialization_alias="authorization_decision",
    )
    reason: str | None = None

    @field_validator("run_id", "tool_name", "reason")
    @classmethod
    def _strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("audit strings cannot be blank")
        return stripped


class AgentRedactedPayload(AithruBaseModel):
    payload: Any
    redaction: AgentRedactionLevel
    redacted_paths: list[str] = Field(default_factory=list)

    @field_validator("redacted_paths")
    @classmethod
    def _redacted_paths_must_not_be_blank(cls, value: list[str]) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        for path in value:
            stripped = path.strip()
            if not stripped:
                raise ValueError("redacted paths cannot contain blank paths")
            if stripped in seen:
                continue
            seen.add(stripped)
            paths.append(stripped)
        return paths

    @model_validator(mode="after")
    def _redaction_must_match_paths(self) -> "AgentRedactedPayload":
        if self.redaction == "none" and self.redacted_paths:
            raise ValueError("redaction none cannot include redacted paths")
        return self


class AgentCapabilityAuditLogEntry(AithruBaseModel):
    source_event_id: str
    source_event_type: str
    sequence: int = Field(ge=0)
    audit: AgentCapabilityAuditEvent

    @field_validator("source_event_id", "source_event_type")
    @classmethod
    def _source_strings_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("audit log source strings cannot be blank")
        return stripped


class AgentCapabilityAuditLog(AithruBaseModel):
    run_id: str
    entries: list[AgentCapabilityAuditLogEntry] = Field(default_factory=list)
    count: int = Field(ge=0)

    @field_validator("run_id")
    @classmethod
    def _run_id_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("audit log run_id cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _count_must_match_entries(self) -> "AgentCapabilityAuditLog":
        if self.count != len(self.entries):
            raise ValueError("audit log count must match entries")
        return self
