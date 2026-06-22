from __future__ import annotations

from aithru_agent.domain import (
    AgentRun,
    AgentRunBudgetStatus,
    AgentRunTreeUsageSnapshot,
    AgentRunUsageSummary,
)
from aithru_agent.domain.usage import aggregate_model_usage_payloads, evaluate_budget_status
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.stream.events import AgentStreamEvent


LINEAGE_CHILD_EVENT_TYPES = {
    "operator_action.follow_up.created",
    "research.continuation.created",
}


async def build_run_usage_summary(
    run: AgentRun,
    event_store: AgentEventStore,
) -> AgentRunUsageSummary:
    events = await event_store.list_by_run(run.id)
    return aggregate_model_usage_payloads(
        run.id,
        [
            event.payload
            for event in events
            if event.type == "model.usage" and isinstance(event.payload, dict)
        ],
        budget_policy=run.harness_options.budget_policy if run.harness_options else None,
        model_cost_policy=(
            run.harness_options.model_cost_policy if run.harness_options else None
        ),
    )


async def build_run_tree_usage_snapshot(
    root_run: AgentRun,
    store: AgentStore,
    event_store: AgentEventStore,
) -> AgentRunTreeUsageSnapshot:
    runs_by_id = {run.id: run for run in await store.list_runs()}
    runs_by_id[root_run.id] = root_run
    ordered_run_ids: list[str] = []
    summaries_by_id: dict[str, AgentRunUsageSummary] = {}
    visiting: set[str] = set()

    async def visit(run: AgentRun) -> AgentRunUsageSummary:
        if run.id in summaries_by_id:
            return summaries_by_id[run.id]
        if run.id in visiting:
            return await build_run_usage_summary(run, event_store)
        visiting.add(run.id)
        ordered_run_ids.append(run.id)
        direct = await build_run_usage_summary(run, event_store)
        child_summaries: list[AgentRunUsageSummary] = []
        subagents = await store.list_subagent_runs(parent_run_id=run.id)
        child_run_ids = [
            subagent.child_run_id
            for subagent in sorted(subagents, key=lambda item: item.id)
        ]
        child_run_ids.extend(
            _lineage_child_run_ids(await event_store.list_by_run(run.id))
        )
        seen_child_run_ids: set[str] = set()
        for child_run_id in child_run_ids:
            if child_run_id in seen_child_run_ids:
                continue
            seen_child_run_ids.add(child_run_id)
            if child_run_id in visiting or child_run_id in summaries_by_id:
                continue
            child = runs_by_id.get(child_run_id) or await store.get_run(child_run_id)
            if child is None:
                continue
            runs_by_id[child.id] = child
            child_summaries.append(await visit(child))
        summary = _with_descendant_usage(direct, child_summaries)
        summaries_by_id[run.id] = summary
        visiting.remove(run.id)
        return summary

    root_summary = await visit(root_run)
    summaries = [summaries_by_id[run_id] for run_id in ordered_run_ids if run_id in summaries_by_id]
    return AgentRunTreeUsageSnapshot(
        root_run_id=root_run.id,
        runs=summaries,
        total_requests=root_summary.total_requests,
        total_tokens=root_summary.total_tokens,
        total_model_cost_usd=root_summary.total_model_cost_usd,
        budget_status=_worst_budget_status(summaries),
        warnings=sorted({warning for summary in summaries for warning in summary.warnings}),
    )


def _with_descendant_usage(
    summary: AgentRunUsageSummary,
    child_summaries: list[AgentRunUsageSummary],
) -> AgentRunUsageSummary:
    descendant_requests = sum(child.total_requests for child in child_summaries)
    descendant_total_tokens = sum(child.total_tokens for child in child_summaries)
    descendant_model_cost_usd = sum(child.total_model_cost_usd for child in child_summaries)
    budget_status, warnings = evaluate_budget_status(
        requests=summary.own_requests + descendant_requests + summary.external_requests,
        total_tokens=summary.own_total_tokens
        + descendant_total_tokens
        + summary.external_total_tokens,
        model_cost_usd=summary.own_model_cost_usd
        + descendant_model_cost_usd
        + summary.external_model_cost_usd,
        budget_policy=summary.budget_policy,
        model_cost_policy=summary.model_cost_policy,
    )
    return summary.model_copy(
        update={
            "descendant_requests": descendant_requests,
            "descendant_input_tokens": sum(
                child.own_input_tokens + child.descendant_input_tokens
                for child in child_summaries
            ),
            "descendant_output_tokens": sum(
                child.own_output_tokens + child.descendant_output_tokens
                for child in child_summaries
            ),
            "descendant_total_tokens": descendant_total_tokens,
            "descendant_model_cost_usd": descendant_model_cost_usd,
            "budget_status": budget_status,
            "warnings": warnings,
        }
    )


def _lineage_child_run_ids(events: list[AgentStreamEvent]) -> list[str]:
    child_run_ids: list[str] = []
    for event in events:
        if event.type not in LINEAGE_CHILD_EVENT_TYPES or not isinstance(event.payload, dict):
            continue
        child_run_id = event.payload.get("child_run_id")
        if isinstance(child_run_id, str) and child_run_id:
            child_run_ids.append(child_run_id)
    return child_run_ids


def _worst_budget_status(
    summaries: list[AgentRunUsageSummary],
) -> AgentRunBudgetStatus:
    if any(summary.budget_status == "exceeded" for summary in summaries):
        return "exceeded"
    if any(summary.budget_status == "warning" for summary in summaries):
        return "warning"
    return "ok"
