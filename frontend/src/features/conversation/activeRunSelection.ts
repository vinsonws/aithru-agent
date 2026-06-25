import type { AgentRun } from "@/lib/api";

export interface SelectedRunRef {
  threadId: string;
  runId: string;
}

export function resolveActiveRunId({
  threadId,
  routeRunId,
  selectedRun,
  runs,
}: {
  threadId: string | null;
  routeRunId: string | null;
  selectedRun: SelectedRunRef | null;
  runs?: AgentRun[];
}): string | null {
  if (!threadId) return null;
  if (routeRunId) return routeRunId;
  if (selectedRun?.threadId === threadId) return selectedRun.runId;
  const threadRuns = runs?.filter((run) => !run.thread_id || run.thread_id === threadId) ?? [];
  if (!threadRuns.length) return null;
  return threadRuns[threadRuns.length - 1].id;
}
