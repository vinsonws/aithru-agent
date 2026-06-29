import { describe, it, expect } from "vitest";
import { formatSseEvent, formatSseComment } from "../../src/stream/sse.js";
import type { AgentStreamEvent } from "../../src/contracts/types.js";

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
