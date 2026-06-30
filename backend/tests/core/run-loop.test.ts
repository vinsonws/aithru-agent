import { describe, it, expect } from "vitest";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import { TestCapabilityRouter } from "@aithru-agent/capabilities";
import { RunLoop } from "@aithru-agent/harness";
import type { AgentRun } from "@aithru-agent/contracts";

function createTestRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run_test_1",
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_test_1",
    task_msg: "Test task",
    scopes: ["*"],
    harness_options: null,
    status: "queued",
    started_at: new Date().toISOString().replace(/\.\d{3}/, ""),
    completed_at: null,
    claim: null,
    result: null,
    error: null,
    ...overrides,
  };
}

describe("RunLoop", () => {
  it("emits run started and transitions to running", () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new TestCapabilityRouter(store);
    const run = createTestRun();
    store.createRun(run);

    const loop = new RunLoop({ run, store, eventWriter, capabilityRouter: router });
    loop.emitRunStarted();

    const updated = store.getRun("run_test_1")!;
    expect(updated.status).toBe("running");

    const events = store.listEvents("run_test_1");
    expect(events.some((e) => e.type === EVENT_TYPES.RUN_STARTED)).toBe(true);
  });

  it("emits run completed and sets result", () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new TestCapabilityRouter(store);
    const run = createTestRun();
    store.createRun(run);

    const loop = new RunLoop({ run, store, eventWriter, capabilityRouter: router });
    loop.emitRunStarted();
    loop.emitRunCompleted({ content: "Done!" });

    const updated = store.getRun("run_test_1")!;
    expect(updated.status).toBe("completed");
    expect(updated.completed_at).toBeTruthy();
    expect(updated.result).toEqual({
      content: "Done!",
      workspace_paths: [],
      message_id: null,
      thread_message_id: null,
    });
  });

  it("emits run failed and sets error", () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new TestCapabilityRouter(store);
    const run = createTestRun();
    store.createRun(run);

    const loop = new RunLoop({ run, store, eventWriter, capabilityRouter: router });
    loop.emitRunStarted();
    loop.emitRunFailed({ code: "TEST_ERROR", message: "Something broke" });

    const updated = store.getRun("run_test_1")!;
    expect(updated.status).toBe("failed");
    expect(updated.error).toEqual({ code: "TEST_ERROR", message: "Something broke" });
  });

  it("executes a tool call and emits all lifecycle events", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new TestCapabilityRouter(store);
    const run = createTestRun();
    store.createRun(run);

    const loop = new RunLoop({ run, store, eventWriter, capabilityRouter: router });
    loop.emitRunStarted();

    await loop.executeToolCall({
      name: "todo.create",
      input: { title: "Test todo" },
    });

    const events = store.listEvents("run_test_1");
    const eventTypes = events.map((e) => e.type);

    expect(eventTypes).toContain(EVENT_TYPES.TOOL_PROPOSED);
    expect(eventTypes).toContain(EVENT_TYPES.TOOL_STARTED);
    expect(eventTypes).toContain(EVENT_TYPES.TOOL_COMPLETED);
  });

  it("emits tool.denied for unknown tools", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new TestCapabilityRouter(store);
    const run = createTestRun();
    store.createRun(run);

    const loop = new RunLoop({ run, store, eventWriter, capabilityRouter: router });
    loop.emitRunStarted();

    const callResult = await loop.executeToolCall({
      name: "nonexistent.tool",
      input: {},
    });

    expect(callResult.result).toBeTruthy();
    expect(callResult.result!.error).toBeTruthy();
    expect(callResult.result!.error!.code).toBe("TOOL_DENIED");

    const events = store.listEvents("run_test_1");
    expect(events.some((e) => e.type === EVENT_TYPES.TOOL_DENIED)).toBe(true);
  });

  it("emits complete message lifecycle", () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new TestCapabilityRouter(store);
    const run = createTestRun();
    store.createRun(run);

    const loop = new RunLoop({ run, store, eventWriter, capabilityRouter: router });
    loop.emitRunStarted();

    const msgId = "msg_test_1";
    loop.emitMessageCreated(msgId, "");
    loop.emitMessageDelta(msgId, "Hello", "Hello");
    loop.emitMessageDelta(msgId, " world", "Hello world");
    loop.emitMessageCompleted(msgId, "Hello world");

    const events = store.listEvents("run_test_1");
    expect(events.some((e) => e.type === EVENT_TYPES.MESSAGE_CREATED)).toBe(true);
    expect(events.filter((e) => e.type === EVENT_TYPES.MESSAGE_DELTA)).toHaveLength(2);
    expect(events.some((e) => e.type === EVENT_TYPES.MESSAGE_COMPLETED)).toBe(true);
  });
});
