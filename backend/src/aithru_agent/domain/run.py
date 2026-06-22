from datetime import UTC, datetime, timedelta
from enum import StrEnum
import re
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel
from .errors import AgentError
from .usage import AgentRunBudgetPolicy, AgentRunModelCostPolicy


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_SUBAGENT = "waiting_subagent"
    WAITING_INPUT = "waiting_input"
    WAITING_EXTERNAL_RUN = "waiting_external_run"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES = frozenset(
    {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    }
)

RUN_STATUS_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    AgentRunStatus.QUEUED: frozenset(
        {
            AgentRunStatus.RUNNING,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.QUEUED,
            AgentRunStatus.WAITING_APPROVAL,
            AgentRunStatus.WAITING_SUBAGENT,
            AgentRunStatus.WAITING_INPUT,
            AgentRunStatus.WAITING_EXTERNAL_RUN,
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.WAITING_APPROVAL: frozenset(
        {
            AgentRunStatus.QUEUED,
            AgentRunStatus.RUNNING,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.WAITING_SUBAGENT: frozenset(
        {
            AgentRunStatus.RUNNING,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.WAITING_INPUT: frozenset(
        {
            AgentRunStatus.QUEUED,
            AgentRunStatus.RUNNING,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.WAITING_EXTERNAL_RUN: frozenset(
        {
            AgentRunStatus.QUEUED,
            AgentRunStatus.RUNNING,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.COMPLETED: frozenset(),
    AgentRunStatus.FAILED: frozenset(),
    AgentRunStatus.CANCELLED: frozenset(),
}


def validate_run_status_transition(
    current: AgentRunStatus | str,
    next_status: AgentRunStatus | str,
) -> AgentRunStatus:
    current_status = AgentRunStatus(current)
    target_status = AgentRunStatus(next_status)
    if current_status == target_status:
        return target_status
    if current_status in TERMINAL_RUN_STATUSES:
        raise AgentError(
            "INVALID_RUN_STATUS_TRANSITION",
            f"Cannot transition terminal run from {current_status} to {target_status}",
        )
    if target_status not in RUN_STATUS_TRANSITIONS[current_status]:
        raise AgentError(
            "INVALID_RUN_STATUS_TRANSITION",
            f"Invalid run status transition from {current_status} to {target_status}",
        )
    return target_status


class AgentRunSource(StrEnum):
    CHAT = "chat"
    SKILL = "skill"
    API = "api"
    WORKBENCH_NODE = "workbench_node"
    DELEGATED_TASK = "delegated_task"


class AgentRunResearchContinuationOptions(AithruBaseModel):
    source_run_id: str = Field(min_length=1)
    continuation_status: str = Field(min_length=1)
    query: str | None = None
    action_ids: list[str] = Field(default_factory=list)
    target_section_ids: list[str] = Field(default_factory=list)

    @field_validator("source_run_id", "continuation_status")
    @classmethod
    def _required_strings_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("research continuation option strings cannot be blank")
        return stripped

    @field_validator("query")
    @classmethod
    def _query_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("action_ids")
    @classmethod
    def _action_ids_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(value, label="research continuation action id")

    @field_validator("target_section_ids")
    @classmethod
    def _target_section_ids_must_be_stable_slugs(cls, value: list[str]) -> list[str]:
        section_ids = _dedupe_nonblank_strings(value, label="target research section id")
        for section_id in section_ids:
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", section_id):
                raise ValueError("target research section id must be a stable lowercase slug")
        return section_ids


class AgentRunOperatorFollowUpOptions(AithruBaseModel):
    source_run_id: str = Field(min_length=1)
    action_kind: str = Field(min_length=1)
    action_label: str = Field(min_length=1)
    action_reason: str = Field(min_length=1)
    action_ids: list[str] = Field(default_factory=list)
    sandbox_run_ids: list[str] = Field(default_factory=list)
    workspace_paths: list[str] = Field(default_factory=list)
    method: Literal["GET", "POST"] | None = None
    path: str | None = None

    @field_validator("source_run_id", "action_kind", "action_label", "action_reason")
    @classmethod
    def _required_strings_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("operator follow-up option strings cannot be blank")
        return stripped

    @field_validator("action_ids")
    @classmethod
    def _action_ids_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(value, label="operator follow-up action id")

    @field_validator("sandbox_run_ids")
    @classmethod
    def _sandbox_run_ids_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(value, label="operator follow-up sandbox run id")

    @field_validator("workspace_paths")
    @classmethod
    def _workspace_paths_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(value, label="operator follow-up workspace path")

    @field_validator("path")
    @classmethod
    def _path_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class AgentModelCapabilities(AithruBaseModel):
    vision: bool = False
    thinking: bool = False


class AgentRunHarnessOptions(AithruBaseModel):
    model: str | None = None
    model_profile_key: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    instructions: str | None = None
    model_capabilities: AgentModelCapabilities | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    model_cost_policy: AgentRunModelCostPolicy | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    budget_policy: AgentRunBudgetPolicy | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    research_continuation: AgentRunResearchContinuationOptions | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    operator_follow_up: AgentRunOperatorFollowUpOptions | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @field_validator("model", "model_profile_key", "instructions")
    @classmethod
    def _optional_strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("run harness option strings cannot be blank")
        return stripped


class AgentRunResult(AithruBaseModel):
    content: str | None = None
    artifact_ids: list[str] = []
    message_id: str | None = None
    thread_message_id: str | None = None


class AgentExternalApprovalRef(AithruBaseModel):
    kind: Literal["workflow_capability"]
    capability_key: str
    capability_run_id: str
    approval_id: str
    tool_call_id: str
    tool_name: str
    correlation_id: str | None = None
    status: Literal["pending", "resolved"] = "pending"

    @field_validator(
        "capability_key",
        "capability_run_id",
        "approval_id",
        "tool_call_id",
        "tool_name",
        "correlation_id",
    )
    @classmethod
    def _strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("external approval ref strings cannot be blank")
        return stripped


class AgentExternalRunWaitRef(AithruBaseModel):
    kind: Literal["workflow_capability"]
    capability_key: str
    capability_run_id: str
    tool_call_id: str
    tool_name: str
    correlation_id: str | None = None
    status: Literal["running"] = "running"

    @field_validator(
        "capability_key",
        "capability_run_id",
        "tool_call_id",
        "tool_name",
        "correlation_id",
    )
    @classmethod
    def _strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("external run ref strings cannot be blank")
        return stripped


class AgentRunRetryPolicy(AithruBaseModel):
    max_attempts: int = Field(default=1, ge=1, le=10)
    initial_delay_seconds: int = Field(default=0, ge=0)
    max_delay_seconds: int = Field(default=300, ge=0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)

    @model_validator(mode="after")
    def _max_delay_must_cover_initial_delay(self) -> Self:
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max_delay_seconds must be greater than or equal to initial_delay_seconds")
        return self

    def can_retry_after_failure(self, failure_attempt: int) -> bool:
        return failure_attempt < self.max_attempts

    def delay_seconds_for_attempt(self, failure_attempt: int) -> int:
        if failure_attempt <= 1:
            return self.initial_delay_seconds
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** (failure_attempt - 1))
        return min(self.max_delay_seconds, int(delay))

    def next_retry_at(self, *, failure_attempt: int, failed_at: str | None = None) -> str:
        failed_at_value = _parse_timestamp(failed_at) if failed_at else datetime.now(UTC)
        return _format_timestamp(
            failed_at_value + timedelta(seconds=self.delay_seconds_for_attempt(failure_attempt))
        )


class AgentRunRetryState(AithruBaseModel):
    attempt: int = Field(default=0, ge=0)
    next_retry_at: str | None = None
    last_error: dict[str, str] | None = None

    def ready_for_claim_at(self, timestamp: str | None = None) -> bool:
        if self.next_retry_at is None:
            return True
        reference = _parse_timestamp(timestamp) if timestamp else datetime.now(UTC)
        return _parse_timestamp(self.next_retry_at) <= reference


class AgentRunClaim(AithruBaseModel):
    worker_id: str = Field(min_length=1)
    claimed_at: str
    last_heartbeat_at: str | None = None
    lease_expires_at: str
    attempt: int = Field(ge=1)

    @model_validator(mode="after")
    def _lease_must_expire_after_claim(self) -> Self:
        claimed_at = _parse_timestamp(self.claimed_at)
        heartbeat_at = _parse_timestamp(self.last_heartbeat_at) if self.last_heartbeat_at else None
        lease_expires_at = _parse_timestamp(self.lease_expires_at)
        if heartbeat_at is not None and heartbeat_at < claimed_at:
            raise ValueError("last_heartbeat_at must be on or after claimed_at")
        if lease_expires_at <= (heartbeat_at or claimed_at):
            raise ValueError("lease_expires_at must be after claimed_at or last_heartbeat_at")
        return self

    @classmethod
    def create(
        cls,
        *,
        worker_id: str,
        claimed_at: str | None = None,
        lease_seconds: int = 300,
        previous_attempt: int = 0,
    ) -> "AgentRunClaim":
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be greater than zero")
        claimed_at_value = _parse_timestamp(claimed_at) if claimed_at else datetime.now(UTC)
        return cls(
            worker_id=worker_id,
            claimed_at=_format_timestamp(claimed_at_value),
            lease_expires_at=_format_timestamp(
                claimed_at_value + timedelta(seconds=lease_seconds)
            ),
            attempt=previous_attempt + 1,
        )

    def renew(
        self,
        *,
        heartbeat_at: str | None = None,
        lease_seconds: int = 300,
    ) -> "AgentRunClaim":
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be greater than zero")
        heartbeat_at_value = _parse_timestamp(heartbeat_at) if heartbeat_at else datetime.now(UTC)
        return AgentRunClaim.model_validate(
            {
                **self.model_dump(mode="python"),
                "last_heartbeat_at": _format_timestamp(heartbeat_at_value),
                "lease_expires_at": _format_timestamp(
                    heartbeat_at_value + timedelta(seconds=lease_seconds)
                ),
            }
        )

    def expired_at(self, timestamp: str | None = None) -> bool:
        reference = _parse_timestamp(timestamp) if timestamp else datetime.now(UTC)
        return _parse_timestamp(self.lease_expires_at) <= reference


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
    current_external_approval: AgentExternalApprovalRef | None = None
    current_external_run: AgentExternalRunWaitRef | None = None
    claim: AgentRunClaim | None = None
    retry_policy: AgentRunRetryPolicy | None = None
    retry_state: AgentRunRetryState | None = None
    result: AgentRunResult | None = None
    error: dict | None = None


def _dedupe_nonblank_strings(values: list[str], *, label: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = item.strip()
        if not value:
            raise ValueError(f"{label} cannot be blank")
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
