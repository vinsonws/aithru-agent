import { describe, it, expect } from "vitest";
import type { AgentStreamEvent } from "@aithru-agent/contracts";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";

describe("AgentEventWriter", () => {
  it("writes events with correct sequence numbers", () => {
    const store = new InMemoryStore();
    const writer = new AgentEventWriter(store);

    const e1 = writer.write("run_1", null, EVENT_TYPES.RUN_CREATED, {});
    const e2 = writer.write("run_1", null, EVENT_TYPES.RUN_STARTED, {});
    const e3 = writer.write("run_1", null, EVENT_TYPES.RUN_COMPLETED, {});

    expect(e1.sequence).toBe(1);
    expect(e2.sequence).toBe(2);
    expect(e3.sequence).toBe(3);

    const events = store.listEvents("run_1");
    expect(events).toHaveLength(3);
  });

  it("events have unique ids", () => {
    const store = new InMemoryStore();
    const writer = new AgentEventWriter(store);

    const e1 = writer.write("run_1", null, EVENT_TYPES.MESSAGE_DELTA, {});
    const e2 = writer.write("run_1", null, EVENT_TYPES.MESSAGE_DELTA, {});

    expect(e1.id).not.toBe(e2.id);
  });

  it("events have timestamps", () => {
    const store = new InMemoryStore();
    const writer = new AgentEventWriter(store);

    const event = writer.write("run_1", null, EVENT_TYPES.RUN_STARTED, {});
    expect(event.timestamp).toBeTruthy();
    expect(typeof event.timestamp).toBe("string");
  });

  it("separates events by run_id", () => {
    const store = new InMemoryStore();
    const writer = new AgentEventWriter(store);

    writer.write("run_1", null, EVENT_TYPES.RUN_CREATED, {});
    writer.write("run_2", null, EVENT_TYPES.RUN_CREATED, {});

    expect(store.listEvents("run_1")).toHaveLength(1);
    expect(store.listEvents("run_2")).toHaveLength(1);
  });

  it("uses a store-provided next sequence without scanning events", () => {
    const events: AgentStreamEvent[] = [];
    let sequence = 0;
    const store = {
      appendEvent(_runId: string, event: AgentStreamEvent): void {
        events.push(event);
      },
      listEvents(): AgentStreamEvent[] {
        throw new Error("listEvents should not be used to assign event sequences");
      },
      nextEventSequence(): number {
        sequence += 1;
        return sequence;
      },
    };
    const writer = new AgentEventWriter(store);

    const e1 = writer.write("run_1", null, EVENT_TYPES.RUN_CREATED, {});
    const e2 = writer.write("run_1", null, EVENT_TYPES.RUN_STARTED, {});

    expect(e1.sequence).toBe(1);
    expect(e2.sequence).toBe(2);
    expect(events).toHaveLength(2);
  });
});

describe("InMemoryStore event persistence", () => {
  it("listEvents returns empty for non-existent run", () => {
    const store = new InMemoryStore();
    expect(store.listEvents("nonexistent")).toEqual([]);
  });
});
