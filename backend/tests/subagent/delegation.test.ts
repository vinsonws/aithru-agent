import { describe, it, expect } from "vitest";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter } from "@aithru-agent/stream";
import { TestCapabilityRouter } from "@aithru-agent/capabilities";
import { SubagentRunner } from "@aithru-agent/subagents";
import { TestModelAdapter } from "@aithru-agent/model";
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
    expect(child!.workspace_id).toBe(parent.workspace_id);
    expect(child!.harness_options).toMatchObject({
      delegated_from_run_id: parent.id,
      max_model_requests: 15,
      max_tool_executions: 30,
    });
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

  it("runs model-driven delegated work through ModelTurnLoop", async () => {
    const store = new InMemoryStore();
    const writer = new AgentEventWriter(store);
    const router = new TestCapabilityRouter(store);
    const runner = new SubagentRunner(store, writer, router, {
      modelAdapterFactory: () => new TestModelAdapter([
        [
          { type: "text_delta", delta: "Child answer" },
          { type: "completed" },
        ],
      ]),
    });

    const parent = createParentRun({
      id: "run_parent_model",
      thread_id: "thread_parent_model",
      workspace_id: "ws_parent_model",
    });
    store.createRun(parent);

    const result = await runner.delegate(parent, {
      task: "Investigate child task",
      scopes: ["workspace:read"],
    });
    const child = store.getRun(result.run_id)!;

    expect(result.status).toBe("completed");
    expect(result.content).toBe("Child answer");
    expect(child.thread_id).toBe(parent.thread_id);
    expect(child.workspace_id).toBe(parent.workspace_id);
    expect(store.listEvents(child.id).map((event) => event.type)).toEqual(expect.arrayContaining([
      "run.started",
      "message.completed",
      "run.completed",
    ]));
  });
});
