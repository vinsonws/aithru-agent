from aithru_agent.domain import (
    AgentRunBudgetPolicy,
    AgentRunHarnessOptions,
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


def test_usage_contracts_are_exported_and_harness_options_accept_budget_policy() -> None:
    policy = AgentRunBudgetPolicy(max_requests=3, max_total_tokens=30)
    options = AgentRunHarnessOptions(budget_policy=policy)
    summary = AgentRunUsageSummary(run_id="run_1")
    snapshot = AgentRunTreeUsageSnapshot(root_run_id="run_1", runs=[summary])
    counters = AgentUsageCounters(requests=1).add(AgentUsageCounters(total_tokens=2))

    assert options.budget_policy == policy
    assert options.model_dump(mode="json")["budget_policy"] == {
        "max_requests": 3,
        "max_total_tokens": 30,
        "warn_at_ratio": 0.8,
    }
    assert snapshot.runs == [summary]
    assert counters.requests == 1
    assert counters.total_tokens == 2
