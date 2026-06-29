// backend/src/snapshots/tree.ts

import type { AgentStore } from "../persistence/protocols.js";

export interface RunTreeProjection {
  run_id: string;
  status: string;
  task_msg: string;
  subagent_runs: RunTreeProjection[];
}

export function buildRunTree(store: AgentStore, runId: string): RunTreeProjection | undefined {
  const run = store.getRun(runId);
  if (!run) return undefined;

  // Find child runs (subagents)
  const allRuns = store.listRuns();
  const children = allRuns.filter((r) => {
    // A child run references this run in its task context
    return String(r.task_msg).includes(`parent:${runId}`) || (r as any).parent_run_id === runId;
  });

  return {
    run_id: run.id,
    status: String(run.status),
    task_msg: String(run.task_msg),
    subagent_runs: children.map((c) => buildRunTree(store, c.id)!).filter(Boolean),
  };
}
