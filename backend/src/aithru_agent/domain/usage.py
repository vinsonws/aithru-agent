from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import Field, computed_field

from .base import AithruBaseModel


AgentRunBudgetStatus = Literal["ok", "warning", "exceeded"]


class AgentRunBudgetPolicy(AithruBaseModel):
    max_requests: int | None = Field(default=None, ge=0)
    max_total_tokens: int | None = Field(default=None, ge=0)
    warn_at_ratio: float = Field(default=0.8, gt=0, le=1)


class AgentUsageCounters(AithruBaseModel):
    requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    def add(self, other: "AgentUsageCounters") -> "AgentUsageCounters":
        return AgentUsageCounters(
            requests=self.requests + other.requests,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class AgentRunUsageSummary(AithruBaseModel):
    run_id: str
    own_requests: int = Field(default=0, ge=0)
    own_input_tokens: int = Field(default=0, ge=0)
    own_output_tokens: int = Field(default=0, ge=0)
    own_total_tokens: int = Field(default=0, ge=0)
    descendant_requests: int = Field(default=0, ge=0)
    descendant_input_tokens: int = Field(default=0, ge=0)
    descendant_output_tokens: int = Field(default=0, ge=0)
    descendant_total_tokens: int = Field(default=0, ge=0)
    external_requests: int = Field(default=0, ge=0)
    external_total_tokens: int = Field(default=0, ge=0)
    budget_policy: AgentRunBudgetPolicy | None = None
    budget_status: AgentRunBudgetStatus = "ok"
    warnings: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def total_requests(self) -> int:
        return self.own_requests + self.descendant_requests + self.external_requests

    @computed_field
    @property
    def total_tokens(self) -> int:
        return self.own_total_tokens + self.descendant_total_tokens + self.external_total_tokens


class AgentRunTreeUsageSnapshot(AithruBaseModel):
    root_run_id: str
    runs: list[AgentRunUsageSummary] = Field(default_factory=list)
    total_requests: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    budget_status: AgentRunBudgetStatus = "ok"
    warnings: list[str] = Field(default_factory=list)


def aggregate_model_usage_payloads(
    run_id: str,
    payloads: Iterable[Mapping[str, Any]],
    budget_policy: AgentRunBudgetPolicy | None = None,
) -> AgentRunUsageSummary:
    counters = AgentUsageCounters()
    for payload in payloads:
        counters = counters.add(
            AgentUsageCounters(
                requests=_non_negative_int(payload.get("requests")),
                input_tokens=_non_negative_int(payload.get("input_tokens")),
                output_tokens=_non_negative_int(payload.get("output_tokens")),
                total_tokens=_non_negative_int(payload.get("total_tokens")),
            )
        )
    budget_status, warnings = evaluate_budget_status(
        requests=counters.requests,
        total_tokens=counters.total_tokens,
        budget_policy=budget_policy,
    )
    return AgentRunUsageSummary(
        run_id=run_id,
        own_requests=counters.requests,
        own_input_tokens=counters.input_tokens,
        own_output_tokens=counters.output_tokens,
        own_total_tokens=counters.total_tokens,
        budget_policy=budget_policy,
        budget_status=budget_status,
        warnings=warnings,
    )


def evaluate_budget_status(
    *,
    requests: int,
    total_tokens: int,
    budget_policy: AgentRunBudgetPolicy | None,
) -> tuple[AgentRunBudgetStatus, list[str]]:
    if budget_policy is None:
        return "ok", []

    exceeded: list[str] = []
    warnings: list[str] = []
    if budget_policy.max_requests is not None:
        if requests > budget_policy.max_requests:
            exceeded.append("requests_exceeded")
        elif requests >= budget_policy.max_requests * budget_policy.warn_at_ratio:
            warnings.append("requests_near_limit")
    if budget_policy.max_total_tokens is not None:
        if total_tokens > budget_policy.max_total_tokens:
            exceeded.append("total_tokens_exceeded")
        elif total_tokens >= budget_policy.max_total_tokens * budget_policy.warn_at_ratio:
            warnings.append("total_tokens_near_limit")
    if exceeded:
        return "exceeded", exceeded
    if warnings:
        return "warning", warnings
    return "ok", []


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    return 0
