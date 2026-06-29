// backend-ts/src/snapshots/summary.ts

import type { AgentStore } from "../persistence/protocols.js";

export interface RunSummary {
  run_id: string;
  status: string;
  task_msg: string;
  started_at: string;
  completed_at: string | null;
  event_count: number;
  tool_calls: number;
  errors: number;
  workspace_file_count: number;
}

export function buildRunSummary(store: AgentStore, runId: string): RunSummary | undefined {
  const run = store.getRun(runId);
  if (!run) return undefined;

  const events = store.listEvents(runId);
  const toolEvents = events.filter((e) => e.type.startsWith("tool."));
  const errorEvents = events.filter((e) => e.type === "tool.failed" || e.type === "run.failed");

  return {
    run_id: run.id,
    status: String(run.status),
    task_msg: String(run.task_msg),
    started_at: String(run.started_at),
    completed_at: run.completed_at != null ? String(run.completed_at) : null,
    event_count: events.length,
    tool_calls: toolEvents.filter((e) => e.type === "tool.started").length,
    errors: errorEvents.length,
    workspace_file_count: store.listWorkspaceFiles(run.workspace_id).length,
  };
}
