import { describe, it, expect } from "vitest";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter } from "@aithru-agent/stream";
import { TestCapabilityRouter } from "@aithru-agent/capabilities";
import { SubagentRunner } from "@aithru-agent/subagents";
import type { AgentRun } from "@aithru-agent/contracts";

function createParentRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run_parent_1",
    org_id: "org_1",
    actor_user_id: "u1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_parent_1",
    task_msg: "Parent task",
    scopes: ["*"],
    harness_options: null,
    status: "running",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
    ...overrides,
  };
}

describe("SubagentRunner", () => {
  it("delegates and creates a child run", async () => {
    const store = new InMemoryStore();
    const writer = new AgentEventWriter(store);
    const router = new TestCapabilityRouter(store);
    const runner = new SubagentRunner(store, writer, router);

    const parent = createParentRun();
    store.createRun(parent);

    const result = await runner.delegate(parent, {
      task: "Sub task",
      scopes: ["workspace:read"],
    });

    expect(result.run_id).toBeDefined();
    expect(result.status).toBe("queued");

    // Child run should exist in store
    const child = store.getRun(result.run_id);
    expect(child).toBeDefined();
    expect(child!.source).toBe("delegated_task");
    expect(child!.org_id).toBe("org_1");
  });

  it("executes delegated script synchronously", async () => {
    const store = new InMemoryStore();
    const writer = new AgentEventWriter(store);
    const router = new TestCapabilityRouter(store);
    const runner = new SubagentRunner(store, writer, router);

    const parent = createParentRun();
    store.createRun(parent);

    const result = await runner.delegate(
      parent,
      { task: "Do stuff", scopes: ["*"] },
      {
        steps: [{ name: "todo.create", input: { title: "sub-task" } }],
        finalContent: "Sub done",
      },
    );

    expect(result.status).toBe("completed");
    expect(result.content).toBeDefined();
  });
});
