import type { AgentStore } from "@aithru-agent/persistence";
import { listChildRuns } from "./tree.js";

type BudgetStatus = "ok" | "warning" | "exceeded";

interface UsageCounters {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface RunUsageSummary {
  run_id: string;
  own_requests: number;
  own_input_tokens: number;
  own_output_tokens: number;
  own_total_tokens: number;
  descendant_requests: number;
  descendant_input_tokens: number;
  descendant_output_tokens: number;
  descendant_total_tokens: number;
  external_requests: number;
  external_total_tokens: number;
  own_model_cost_usd: number;
  descendant_model_cost_usd: number;
  external_model_cost_usd: number;
  budget_policy: null;
  model_cost_policy: null;
  budget_status: BudgetStatus;
  warnings: string[];
  total_requests: number;
  total_tokens: number;
  total_model_cost_usd: number;
}

export interface RunTreeUsageProjection {
  root_run_id: string;
  runs: RunUsageSummary[];
  total_requests: number;
  total_tokens: number;
  total_model_cost_usd: number;
  budget_status: BudgetStatus;
  warnings: string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function nonNegativeInt(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return 0;
  return Math.trunc(value);
}

function addUsage(a: UsageCounters, b: UsageCounters): UsageCounters {
  return {
    requests: a.requests + b.requests,
    input_tokens: a.input_tokens + b.input_tokens,
    output_tokens: a.output_tokens + b.output_tokens,
    total_tokens: a.total_tokens + b.total_tokens,
  };
}

function usagePayloadCounters(payload: unknown): UsageCounters {
  if (!isRecord(payload)) {
    return { requests: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0 };
  }
  const inputTokens = nonNegativeInt(payload.input_tokens);
  const outputTokens = nonNegativeInt(payload.output_tokens);
  const hasTotalTokens = Object.hasOwn(payload, "total_tokens");
  return {
    requests: nonNegativeInt(payload.requests),
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: hasTotalTokens
      ? nonNegativeInt(payload.total_tokens)
      : inputTokens + outputTokens,
  };
}

function ownUsage(store: AgentStore, runId: string): UsageCounters {
  return store
    .listEvents(runId)
    .filter((event) => event.type === "model.usage")
    .map((event) => usagePayloadCounters(event.payload))
    .reduce(addUsage, { requests: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0 });
}

function ownSummary(runId: string, counters: UsageCounters): RunUsageSummary {
  return {
    run_id: runId,
    own_requests: counters.requests,
    own_input_tokens: counters.input_tokens,
    own_output_tokens: counters.output_tokens,
    own_total_tokens: counters.total_tokens,
    descendant_requests: 0,
    descendant_input_tokens: 0,
    descendant_output_tokens: 0,
    descendant_total_tokens: 0,
    external_requests: 0,
    external_total_tokens: 0,
    own_model_cost_usd: 0,
    descendant_model_cost_usd: 0,
    external_model_cost_usd: 0,
    budget_policy: null,
    model_cost_policy: null,
    budget_status: "ok",
    warnings: [],
    total_requests: counters.requests,
    total_tokens: counters.total_tokens,
    total_model_cost_usd: 0,
  };
}

function sum<T>(items: T[], value: (item: T) => number): number {
  return items.reduce((total, item) => total + value(item), 0);
}

export function buildRunUsageSummary(store: AgentStore, runId: string): RunUsageSummary | undefined {
  if (!store.getRun(runId)) return undefined;
  return ownSummary(runId, ownUsage(store, runId));
}

export function buildRunTreeUsage(store: AgentStore, rootRunId: string): RunTreeUsageProjection | undefined {
  if (!store.getRun(rootRunId)) return undefined;

  const runs: RunUsageSummary[] = [];
  const visiting = new Set<string>();
  const visited = new Set<string>();

  function visit(runId: string): RunUsageSummary | undefined {
    if (visiting.has(runId) || visited.has(runId)) return undefined;
    const summary = buildRunUsageSummary(store, runId);
    if (!summary) return undefined;

    visiting.add(runId);
    visited.add(runId);
    const index = runs.length;
    runs.push(summary);
    const childSummaries = listChildRuns(store, runId)
      .map((child) => visit(child.id))
      .filter((child): child is RunUsageSummary => child != null);
    visiting.delete(runId);

    const descendantRequests = sum(childSummaries, (child) => child.total_requests);
    const descendantInputTokens = sum(
      childSummaries,
      (child) => child.own_input_tokens + child.descendant_input_tokens,
    );
    const descendantOutputTokens = sum(
      childSummaries,
      (child) => child.own_output_tokens + child.descendant_output_tokens,
    );
    const descendantTotalTokens = sum(childSummaries, (child) => child.total_tokens);
    const descendantModelCostUsd = sum(childSummaries, (child) => child.total_model_cost_usd);
    const withDescendants: RunUsageSummary = {
      ...summary,
      descendant_requests: descendantRequests,
      descendant_input_tokens: descendantInputTokens,
      descendant_output_tokens: descendantOutputTokens,
      descendant_total_tokens: descendantTotalTokens,
      descendant_model_cost_usd: descendantModelCostUsd,
      total_requests: summary.own_requests + descendantRequests + summary.external_requests,
      total_tokens: summary.own_total_tokens + descendantTotalTokens + summary.external_total_tokens,
      total_model_cost_usd:
        summary.own_model_cost_usd + descendantModelCostUsd + summary.external_model_cost_usd,
    };
    runs[index] = withDescendants;
    return withDescendants;
  }

  const root = visit(rootRunId);
  if (!root) return undefined;
  return {
    root_run_id: rootRunId,
    runs,
    total_requests: root.total_requests,
    total_tokens: root.total_tokens,
    total_model_cost_usd: root.total_model_cost_usd,
    budget_status: "ok",
    warnings: [],
  };
}
