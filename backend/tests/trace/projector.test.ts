import { describe, it, expect } from "vitest";
import { projectTraceSpans } from "@aithru-agent/trace";
import type { AgentStreamEvent } from "@aithru-agent/contracts";

function makeEvent(overrides: Partial<AgentStreamEvent>): AgentStreamEvent {
  return {
    id: "evt_1", run_id: "run_1", thread_id: null, sequence: 1,
    timestamp: "2026-01-01T00:00:00Z", type: "run.started",
    source: { kind: "system" }, visibility: "user", redaction: "none",
    summary: null, payload: {},
    ...overrides,
  };
}

describe("projectTraceSpans", () => {
  it("produces empty array for no events", () => {
    expect(projectTraceSpans([])).toEqual([]);
  });

  it("creates run span from run.started", () => {
    const spans = projectTraceSpans([
      makeEvent({ id: "e1", type: "run.started", sequence: 1 }),
    ]);
    expect(spans).toHaveLength(1);
    expect(spans[0].kind).toBe("run");
    expect(spans[0].status).toBe("ok");
  });

  it("adds tool spans as children of run", () => {
    const spans = projectTraceSpans([
      makeEvent({ id: "e1", type: "run.started", sequence: 1 }),
      makeEvent({ id: "e2", type: "tool.proposed", sequence: 2, payload: { tool_call_id: "tc1", name: "test.tool" } }),
    ]);
    expect(spans[0].children).toHaveLength(1);
    expect(spans[0].children[0].kind).toBe("tool");
    expect(spans[0].children[0].name).toBe("test.tool");
  });

  it("marks tool as error on tool.failed", () => {
    const spans = projectTraceSpans([
      makeEvent({ id: "e1", type: "run.started", sequence: 1 }),
      makeEvent({ id: "e2", type: "tool.proposed", sequence: 2, payload: { tool_call_id: "tc1", name: "t" } }),
      makeEvent({ id: "e3", type: "tool.failed", sequence: 3, payload: { tool_call_id: "tc1", error: { code: "ERR" } } }),
    ]);
    expect(spans[0].children[0].status).toBe("error");
  });

  it("marks run as completed and error appropriately", () => {
    const okSpans = projectTraceSpans([
      makeEvent({ id: "e1", type: "run.started", sequence: 1 }),
      makeEvent({ id: "e2", type: "run.completed", sequence: 2 }),
    ]);
    expect(okSpans[0].status).toBe("ok");
    expect(okSpans[0].completed_at).toBeTruthy();

    const errSpans = projectTraceSpans([
      makeEvent({ id: "e1", type: "run.started", sequence: 1, run_id: "run_2" }),
      makeEvent({ id: "e2", type: "run.failed", sequence: 2, run_id: "run_2" }),
    ]);
    expect(errSpans[0].status).toBe("error");
  });
});
