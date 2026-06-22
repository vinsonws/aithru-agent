import pytest
from pydantic import ValidationError

from aithru_agent.domain import (
    AgentRunBudgetPolicy,
    AgentRunHarnessOptions,
    AgentRunModelCostPolicy,
    AgentRunTreeUsageSnapshot,
    AgentRunUsageSummary,
    AgentUsageCounters,
)
from aithru_agent.domain.usage import aggregate_model_usage_payloads


def test_aggregate_model_usage_payloads_sums_requests_and_tokens() -> None:
    summary = aggregate_model_usage_payloads(
        "run_1",
        [
            {
                "requests": 1,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            },
            {
                "requests": 2,
                "input_tokens": 20,
                "output_tokens": 7,
                "total_tokens": 27,
            },
        ],
    )

    assert summary.run_id == "run_1"
    assert summary.own_requests == 3
    assert summary.own_input_tokens == 30
    assert summary.own_output_tokens == 12
    assert summary.own_total_tokens == 42
    assert summary.total_requests == 3
    assert summary.total_tokens == 42


def test_aggregate_model_usage_payloads_treats_invalid_values_as_zero() -> None:
    summary = aggregate_model_usage_payloads(
        "run_1",
        [
            {
                "requests": -1,
                "input_tokens": "12",
                "output_tokens": None,
                "total_tokens": -4,
            },
            {},
        ],
    )

    assert summary.own_requests == 0
    assert summary.own_input_tokens == 0
    assert summary.own_output_tokens == 0
    assert summary.own_total_tokens == 0
    assert summary.total_requests == 0
    assert summary.total_tokens == 0


def test_aggregate_model_usage_payloads_reports_budget_warning_and_exceeded() -> None:
    warning = aggregate_model_usage_payloads(
        "run_1",
        [{"requests": 8, "total_tokens": 80}],
        budget_policy=AgentRunBudgetPolicy(max_requests=10, max_total_tokens=100),
    )
    exceeded = aggregate_model_usage_payloads(
        "run_1",
        [{"requests": 11, "total_tokens": 101}],
        budget_policy=AgentRunBudgetPolicy(max_requests=10, max_total_tokens=100),
    )

    assert warning.budget_status == "warning"
    assert warning.warnings == ["requests_near_limit", "total_tokens_near_limit"]
    assert exceeded.budget_status == "exceeded"
    assert exceeded.warnings == ["requests_exceeded", "total_tokens_exceeded"]


def test_aggregate_model_usage_payloads_estimates_and_limits_model_cost() -> None:
    warning = aggregate_model_usage_payloads(
        "run_1",
        [{"requests": 1, "input_tokens": 800_000, "output_tokens": 0}],
        budget_policy=AgentRunBudgetPolicy(),
        model_cost_policy=AgentRunModelCostPolicy(
            input_cost_per_million_tokens_usd=1,
            output_cost_per_million_tokens_usd=2,
            max_cost_usd=1,
        ),
    )
    exceeded = aggregate_model_usage_payloads(
        "run_1",
        [{"requests": 1, "input_tokens": 500_000, "output_tokens": 500_001}],
        model_cost_policy=AgentRunModelCostPolicy(
            input_cost_per_million_tokens_usd=1,
            output_cost_per_million_tokens_usd=2,
            max_cost_usd=1.5,
        ),
    )

    assert warning.own_model_cost_usd == 0.8
    assert warning.budget_status == "warning"
    assert warning.warnings == ["model_cost_near_limit"]
    assert exceeded.own_model_cost_usd == 1.500002
    assert exceeded.budget_status == "exceeded"
    assert exceeded.warnings == ["model_cost_exceeded"]


def test_budget_exceeded_status_preserves_near_limit_warnings() -> None:
    summary = aggregate_model_usage_payloads(
        "run_1",
        [{"requests": 11, "total_tokens": 80}],
        budget_policy=AgentRunBudgetPolicy(max_requests=10, max_total_tokens=100),
    )

    assert summary.budget_status == "exceeded"
    assert summary.warnings == ["requests_exceeded", "total_tokens_near_limit"]


def test_budget_policy_rejects_zero_limits() -> None:
    with pytest.raises(ValidationError):
        AgentRunBudgetPolicy(max_requests=0)

    with pytest.raises(ValidationError):
        AgentRunBudgetPolicy(max_total_tokens=0)


def test_usage_contracts_are_exported_and_harness_options_accept_budget_policy() -> None:
    policy = AgentRunBudgetPolicy(max_requests=3, max_total_tokens=30)
    cost_policy = AgentRunModelCostPolicy(max_cost_usd=0.25)
    options = AgentRunHarnessOptions(budget_policy=policy, model_cost_policy=cost_policy)
    summary = AgentRunUsageSummary(run_id="run_1")
    snapshot = AgentRunTreeUsageSnapshot(root_run_id="run_1", runs=[summary])
    counters = AgentUsageCounters(requests=1).add(AgentUsageCounters(total_tokens=2))

    assert options.budget_policy == policy
    assert options.model_cost_policy == cost_policy
    assert options.model_dump(mode="json")["budget_policy"] == {
        "max_requests": 3,
        "max_total_tokens": 30,
        "warn_at_ratio": 0.8,
    }
    assert snapshot.runs == [summary]
    assert counters.requests == 1
    assert counters.total_tokens == 2
