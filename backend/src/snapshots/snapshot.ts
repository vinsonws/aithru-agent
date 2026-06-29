// backend/src/snapshots/snapshot.ts

import type { AgentStore } from "../persistence/protocols.js";
import type { AgentRun } from "../contracts/types.js";

export interface RunSnapshotResponse {
  run: AgentRun;
  event_count: number;
  workspace_files: Array<{ path: string; size: number }>;
  todos: Array<{ id: string; title: string; status: string }>;
  approvals: Array<{ id: string; tool_name: string; status: string }>;
  artifacts: Array<{ id: string; title: string; status: string }>;
}

export function buildRunSnapshot(store: AgentStore, runId: string): RunSnapshotResponse | undefined {
  const run = store.getRun(runId);
  if (!run) return undefined;

  const events = store.listEvents(runId);
  const files = store.listWorkspaceFiles(run.workspace_id);
  const todos = store.listTodos(runId);
  const artifacts = store.listArtifacts(runId);

  return {
    run,
    event_count: events.length,
    workspace_files: files.map((f) => ({ path: f.path, size: f.size })),
    todos: todos.map((t) => ({ id: t.id, title: t.title, status: t.status })),
    approvals: [], // populated from events
    artifacts: artifacts.map((a) => ({ id: a.id, title: a.title, status: a.status })),
  };
}
