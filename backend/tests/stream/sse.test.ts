import { describe, it, expect } from "vitest";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES, formatSseEvent, formatSseComment } from "@aithru-agent/stream";
import type { AgentStreamEvent } from "@aithru-agent/contracts";

describe("formatSseEvent", () => {
  it("formats an SSE event with id, event, and data", () => {
    const event: AgentStreamEvent = {
      id: "evt_1",
      run_id: "run_1",
      thread_id: "thread_1",
      sequence: 1,
      timestamp: "2026-06-29T00:00:00Z",
      type: "run.started",
      source: { kind: "system" },
      visibility: "user",
      redaction: "none",
      summary: null,
      payload: { status: "running" },
    };
    const result = formatSseEvent(event);

    expect(result).toContain("id: evt_1");
    expect(result).toContain("event: run.started");
    expect(result).toContain("data:");
    expect(result).toMatch(/data: \{"id":"evt_1"/);
  });

  it("ends with double newline", () => {
    const event: AgentStreamEvent = {
      id: "evt_1",
      run_id: "run_1",
      thread_id: null,
      sequence: 1,
      timestamp: "2026-06-29T00:00:00Z",
      type: "run.started",
      source: { kind: "system" },
      visibility: "user",
      redaction: "none",
      summary: null,
      payload: {},
    };
    expect(formatSseEvent(event).endsWith("\n\n")).toBe(true);
  });
});

describe("formatSseComment", () => {
  it("prefixes with colon and ends with double newline", () => {
    const result = formatSseComment("hello world");
    expect(result).toBe(": hello world\n\n");
  });

  it("strips newlines from comment", () => {
    const result = formatSseComment("hello\nworld");
    expect(result).toBe(": hello world\n\n");
  });
});

describe("AgentEventWriter subscriptions", () => {
  it("notifies run subscribers synchronously after writes", () => {
    const store = new InMemoryStore();
    const writer = new AgentEventWriter(store);
    const seen: AgentStreamEvent[] = [];
    const unsubscribe = writer.subscribe("run_1", (event) => {
      seen.push(event);
    });

    const event = writer.write("run_1", null, EVENT_TYPES.RUN_STARTED, { status: "running" });

    expect(seen).toEqual([event]);

    unsubscribe();
    writer.write("run_1", null, EVENT_TYPES.RUN_COMPLETED, { status: "completed" });
    expect(seen).toHaveLength(1);
  });
});
