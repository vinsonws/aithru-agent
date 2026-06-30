import type { AgentStore } from "@aithru-agent/persistence";
import type { AgentRun } from "@aithru-agent/contracts";

export interface RunTreeProjection {
  run_id: string;
  status: string;
  task_msg: string;
  subagent_runs: RunTreeProjection[];
}

export function listChildRuns(store: AgentStore, runId: string): AgentRun[] {
  return store.listRuns().filter((run) => {
    return String(run.task_msg).includes(`parent:${runId}`) || (run as any).parent_run_id === runId;
  });
}

export function buildRunTree(store: AgentStore, runId: string): RunTreeProjection | undefined {
  const run = store.getRun(runId);
  if (!run) return undefined;

  return {
    run_id: run.id,
    status: String(run.status),
    task_msg: String(run.task_msg),
    subagent_runs: listChildRuns(store, runId).map((c) => buildRunTree(store, c.id)!).filter(Boolean),
  };
}
