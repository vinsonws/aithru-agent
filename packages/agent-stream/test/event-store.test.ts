import { describe, it, expect } from "vitest";
import {
  InMemoryAgentEventStore,
  InMemoryAgentEventBus,
  AgentEventWriter,
  createAgentStreamEvent,
} from "../src/index.js";
import type { AgentStreamEvent } from "../src/index.js";
import type { RunId, ThreadId } from "@aithru/agent-core";

function makeEvent(runId: RunId, sequence: number, type: string): AgentStreamEvent {
  return createAgentStreamEvent({
    runId,
    sequence,
    type: type as unknown as AgentStreamEvent["type"],
    source: { kind: "harness" },
    payload: {},
  });
}

describe("InMemoryAgentEventStore", () => {
  it("should append events and sequence should increase", async () => {
    const store = new InMemoryAgentEventStore();
    const runId = "run_1" as RunId;

    await store.append(makeEvent(runId, 1, "run.created"));
    await store.append(makeEvent(runId, 2, "run.started"));
    await store.append(makeEvent(runId, 3, "run.completed"));

    const events = await store.listByRun(runId);
    expect(events).toHaveLength(3);
    expect(events[0]!.sequence).toBe(1);
    expect(events[1]!.sequence).toBe(2);
    expect(events[2]!.sequence).toBe(3);
  });

  it("should return empty array for unknown run", async () => {
    const store = new InMemoryAgentEventStore();
    const events = await store.listByRun("run_unknown" as RunId);
    expect(events).toEqual([]);
  });

  it("listAfterSequence should return events after given sequence", async () => {
    const store = new InMemoryAgentEventStore();
    const runId = "run_2" as RunId;

    await store.append(makeEvent(runId, 1, "run.created"));
    await store.append(makeEvent(runId, 2, "run.started"));
    await store.append(makeEvent(runId, 3, "message.created"));
    await store.append(makeEvent(runId, 4, "run.completed"));

    const after = await store.listAfterSequence(runId, 2);
    expect(after).toHaveLength(2);
    expect(after[0]!.sequence).toBe(3);
    expect(after[1]!.sequence).toBe(4);
  });
});

describe("InMemoryAgentEventBus", () => {
  it("should deliver events to subscribers", async () => {
    const bus = new InMemoryAgentEventBus();
    const runId = "run_3" as RunId;

    const received: AgentStreamEvent[] = [];
    bus.subscribe(runId, (e) => received.push(e));

    const event = makeEvent(runId, 1, "run.created");
    bus.publish(event);

    expect(received).toHaveLength(1);
    expect(received[0]!.sequence).toBe(1);
  });

  it("should not deliver to unsubscribed", async () => {
    const bus = new InMemoryAgentEventBus();
    const runId = "run_4" as RunId;

    const received: AgentStreamEvent[] = [];
    const fn = (e: AgentStreamEvent) => received.push(e);
    bus.subscribe(runId, fn);
    bus.unsubscribe(runId, fn);

    bus.publish(makeEvent(runId, 1, "run.created"));
    expect(received).toHaveLength(0);
  });

  it("should not deliver to different run subscribers", async () => {
    const bus = new InMemoryAgentEventBus();
    const received: AgentStreamEvent[] = [];
    bus.subscribe("run_a" as RunId, (e) => received.push(e));

    bus.publish(makeEvent("run_b" as RunId, 1, "run.created"));
    expect(received).toHaveLength(0);
  });
});

describe("AgentEventWriter", () => {
  it("should increment sequence on each write", async () => {
    const store = new InMemoryAgentEventStore();
    const bus = new InMemoryAgentEventBus();
    const writer = new AgentEventWriter(store, bus);

    const runId = "run_5" as RunId;

    const e1 = await writer.write({
      runId,
      type: "run.created",
      source: { kind: "harness" },
      visibility: "user",
      redaction: "none",
      payload: {},
      timestamp: new Date().toISOString(),
    });

    const e2 = await writer.write({
      runId,
      type: "run.started",
      source: { kind: "harness" },
      visibility: "user",
      redaction: "none",
      payload: {},
      timestamp: new Date().toISOString(),
    });

    expect(e1.sequence).toBe(1);
    expect(e2.sequence).toBe(2);
  });

  it("should persist before publish", async () => {
    const store = new InMemoryAgentEventStore();
    const bus = new InMemoryAgentEventBus();
    const writer = new AgentEventWriter(store, bus);

    const runId = "run_6" as RunId;
    let publishedEvent: AgentStreamEvent | null = null;
    bus.subscribe(runId, (e) => { publishedEvent = e; });

    await writer.write({
      runId,
      type: "run.created",
      source: { kind: "harness" },
      visibility: "user",
      redaction: "none",
      payload: {},
      timestamp: new Date().toISOString(),
    });

    // After publish, event should be in store
    const stored = await store.listByRun(runId);
    expect(stored).toHaveLength(1);
    expect(publishedEvent).not.toBeNull();
  });

  it("resetSequence should reset the counter", async () => {
    const store = new InMemoryAgentEventStore();
    const bus = new InMemoryAgentEventBus();
    const writer = new AgentEventWriter(store, bus);

    const runId = "run_7" as RunId;

    await writer.write({
      runId,
      type: "run.created",
      source: { kind: "harness" },
      visibility: "user",
      redaction: "none",
      payload: {},
      timestamp: new Date().toISOString(),
    });

    writer.resetSequence();

    const e2 = await writer.write({
      runId,
      type: "run.started",
      source: { kind: "harness" },
      visibility: "user",
      redaction: "none",
      payload: {},
      timestamp: new Date().toISOString(),
    });

    expect(e2.sequence).toBe(1);
  });
});
