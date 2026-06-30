import { describe, it, expect } from "vitest";
import { InMemoryStore } from "@aithru-agent/persistence";
import {
  buildRunSnapshot,
  buildRunSummary,
  buildRunTree,
  buildRunTreeUsage,
  buildRunUsageSummary,
} from "@aithru-agent/snapshots";
import type { AgentRun } from "@aithru-agent/contracts";

function createRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run_snap_1",
    org_id: "org_1",
    actor_user_id: "u1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_snap_1",
    task_msg: "Snap test",
    scopes: ["*"],
    harness_options: null,
    status: "completed",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: "2026-01-01T00:01:00Z",
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
    ...overrides,
  };
}

describe("buildRunSnapshot", () => {
  it("returns undefined for missing run", () => {
    const store = new InMemoryStore();
    expect(buildRunSnapshot(store, "nonexistent")).toBeUndefined();
  });

  it("builds snapshot with events, files, and todos", () => {
    const store = new InMemoryStore();
    const run = createRun();
    store.createRun(run);

    // Add events
    store.appendEvent(run.id, {
      id: "evt_1",
      run_id: run.id,
      thread_id: null,
      sequence: 1,
      timestamp: "2026-01-01T00:00:00Z",
      type: "run.started",
      source: { kind: "system" },
      visibility: "user" as const,
      redaction: "none" as const,
      summary: null,
      payload: {},
    });

    // Add workspace files
    store.writeFile(run.workspace_id, "/a.txt", "content");

    // Add todos
    store.createTodo({
      id: "todo_1",
      run_id: run.id,
      title: "Task 1",
      status: "pending",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    const snap = buildRunSnapshot(store, run.id);
    expect(snap).toBeDefined();
    expect(snap!.run.id).toBe(run.id);
    expect(snap!.event_count).toBe(1);
    expect(snap!.workspace_files).toEqual([{ path: "/a.txt", size: 7 }]);
    expect(snap!.todos).toEqual([
      { id: "todo_1", title: "Task 1", status: "pending" },
    ]);
    expect("artifacts" in snap!).toBe(false);
  });
});

describe("buildRunSummary", () => {
  it("returns undefined for missing run", () => {
    const store = new InMemoryStore();
    expect(buildRunSummary(store, "nonexistent")).toBeUndefined();
  });

  it("summarizes run with tool calls and errors", () => {
    const store = new InMemoryStore();
    const run = createRun();
    store.createRun(run);

    store.appendEvent(run.id, {
      id: "evt_1",
      run_id: run.id,
      thread_id: null,
      sequence: 1,
      timestamp: "2026-01-01T00:00:00Z",
      type: "tool.started",
      source: { kind: "system" },
      visibility: "user" as const,
      redaction: "none" as const,
      summary: null,
      payload: {},
    });
    store.appendEvent(run.id, {
      id: "evt_2",
      run_id: run.id,
      thread_id: null,
      sequence: 2,
      timestamp: "2026-01-01T00:00:01Z",
      type: "tool.failed",
      source: { kind: "system" },
      visibility: "user" as const,
      redaction: "none" as const,
      summary: null,
      payload: {},
    });

    const summary = buildRunSummary(store, run.id);
    expect(summary).toBeDefined();
    expect(summary!.run_id).toBe(run.id);
    expect(summary!.status).toBe("completed");
    expect(summary!.event_count).toBe(2);
    expect(summary!.tool_calls).toBe(1);
    expect(summary!.errors).toBe(1);
  });
});

describe("buildRunTree", () => {
  it("returns undefined for missing run", () => {
    const store = new InMemoryStore();
    expect(buildRunTree(store, "nonexistent")).toBeUndefined();
  });

  it("builds tree for single run", () => {
    const store = new InMemoryStore();
    const run = createRun();
    store.createRun(run);

    const tree = buildRunTree(store, run.id);
    expect(tree).toBeDefined();
    expect(tree!.run_id).toBe(run.id);
    expect(tree!.subagent_runs).toEqual([]);
  });

  it("includes child subagent runs", () => {
    const store = new InMemoryStore();
    const parent = createRun({ id: "parent" });
    const child = createRun({
      id: "child",
      task_msg: "Subagent task parent:parent",
    } as any);
    store.createRun(parent);
    store.createRun(child);

    const tree = buildRunTree(store, parent.id);
    expect(tree).toBeDefined();
    expect(tree!.subagent_runs.length).toBe(1);
    expect(tree!.subagent_runs[0].run_id).toBe("child");
  });
});

describe("run usage projections", () => {
  it("sums own model usage events", () => {
    const store = new InMemoryStore();
    const run = createRun();
    store.createRun(run);
    store.appendEvent(run.id, {
      id: "evt_usage_1",
      run_id: run.id,
      thread_id: null,
      sequence: 1,
      timestamp: "2026-01-01T00:00:00Z",
      type: "model.usage",
      source: { kind: "model" },
      visibility: "audit" as const,
      redaction: "none" as const,
      summary: null,
      payload: { requests: 1, input_tokens: 10, output_tokens: 5 },
    });
    store.appendEvent(run.id, {
      id: "evt_usage_2",
      run_id: run.id,
      thread_id: null,
      sequence: 2,
      timestamp: "2026-01-01T00:00:01Z",
      type: "model.usage",
      source: { kind: "model" },
      visibility: "audit" as const,
      redaction: "none" as const,
      summary: null,
      payload: { requests: 2, input_tokens: 3, output_tokens: 4, total_tokens: 9 },
    });

    const usage = buildRunUsageSummary(store, run.id);

    expect(usage).toMatchObject({
      run_id: run.id,
      own_requests: 3,
      own_input_tokens: 13,
      own_output_tokens: 9,
      own_total_tokens: 24,
      total_requests: 3,
      total_tokens: 24,
    });
  });

  it("ignores legacy camelCase token fields", () => {
    const store = new InMemoryStore();
    const run = createRun();
    store.createRun(run);
    store.appendEvent(run.id, {
      id: "evt_usage_legacy",
      run_id: run.id,
      thread_id: null,
      sequence: 1,
      timestamp: "2026-01-01T00:00:00Z",
      type: "model.usage",
      source: { kind: "model" },
      visibility: "audit" as const,
      redaction: "none" as const,
      summary: null,
      payload: { requests: 1, inputTokens: 10, outputTokens: 5, totalTokens: 15 },
    });

    const usage = buildRunUsageSummary(store, run.id);

    expect(usage).toMatchObject({
      own_requests: 1,
      own_input_tokens: 0,
      own_output_tokens: 0,
      own_total_tokens: 0,
      total_tokens: 0,
    });
  });

  it("rolls child run usage into tree totals", () => {
    const store = new InMemoryStore();
    const parent = createRun({ id: "parent" });
    const child = createRun({ id: "child", task_msg: "Subagent task parent:parent" } as any);
    store.createRun(parent);
    store.createRun(child);
    store.appendEvent(parent.id, {
      id: "evt_parent_usage",
      run_id: parent.id,
      thread_id: null,
      sequence: 1,
      timestamp: "2026-01-01T00:00:00Z",
      type: "model.usage",
      source: { kind: "model" },
      visibility: "audit" as const,
      redaction: "none" as const,
      summary: null,
      payload: { requests: 1, total_tokens: 6 },
    });
    store.appendEvent(child.id, {
      id: "evt_child_usage",
      run_id: child.id,
      thread_id: null,
      sequence: 1,
      timestamp: "2026-01-01T00:00:01Z",
      type: "model.usage",
      source: { kind: "model" },
      visibility: "audit" as const,
      redaction: "none" as const,
      summary: null,
      payload: { requests: 2, total_tokens: 14 },
    });

    const usage = buildRunTreeUsage(store, parent.id);

    expect(usage?.total_requests).toBe(3);
    expect(usage?.total_tokens).toBe(20);
    expect(usage?.runs.map((runUsage) => runUsage.run_id)).toEqual(["parent", "child"]);
    expect(usage?.runs[0]).toMatchObject({
      own_requests: 1,
      descendant_requests: 2,
      total_tokens: 20,
    });
  });
});
