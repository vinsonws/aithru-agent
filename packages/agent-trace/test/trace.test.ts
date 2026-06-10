import { describe, it, expect } from "vitest";
import { projectTraceSpans } from "../src/index.js";
import type { AgentStreamEvent } from "@aithru/agent-stream";
import type { RunId, EventId } from "@aithru/agent-core";

function ev(overrides: Partial<AgentStreamEvent> & { type: AgentStreamEvent["type"] }): AgentStreamEvent {
  return {
    id: "e1" as EventId,
    runId: "run_1" as RunId,
    sequence: 1,
    timestamp: new Date("2025-01-01T00:00:00Z").toISOString(),
    source: { kind: "harness" },
    visibility: "user",
    redaction: "none",
    payload: {},
    ...overrides,
  };
}

describe("projectTraceSpans", () => {
  it("should produce a completed run span from run.created + run.completed", () => {
    const events = [
      ev({ type: "run.created", sequence: 1 }),
      ev({ type: "run.started", sequence: 2 }),
      ev({ type: "run.completed", sequence: 3 }),
    ];
    const spans = projectTraceSpans(events);
    const runSpan = spans.find((s) => s.kind === "run");
    expect(runSpan).toBeDefined();
    expect(runSpan!.status).toBe("completed");
    expect(runSpan!.eventIds).toHaveLength(2); // created + completed
  });

  it("should mark run span as failed on run.failed", () => {
    const events = [
      ev({ type: "run.created", sequence: 1 }),
      ev({ type: "run.failed", sequence: 2 }),
    ];
    const spans = projectTraceSpans(events);
    expect(spans.find((s) => s.kind === "run")!.status).toBe("failed");
  });

  it("should produce a tool span from tool.proposed + tool.completed", () => {
    const events = [
      ev({ type: "run.created", sequence: 1 }),
      ev({ type: "tool.proposed", sequence: 2, payload: { toolCallId: "tc_1", toolName: "workspace.listFiles" } }),
      ev({ type: "tool.started", sequence: 3 }),
      ev({ type: "tool.completed", sequence: 4, payload: { toolCallId: "tc_1", toolName: "workspace.listFiles" } }),
    ];
    const spans = projectTraceSpans(events);
    const toolSpan = spans.find((s) => s.kind === "tool");
    expect(toolSpan).toBeDefined();
    expect(toolSpan!.status).toBe("completed");
    expect(toolSpan!.refs?.toolCallId).toBe("tc_1");
  });

  it("should produce an approval span from approval.requested + resolved", () => {
    const events = [
      ev({ type: "run.created", sequence: 1 }),
      ev({ type: "approval.requested", sequence: 2, payload: { approvalId: "app_1" } }),
      ev({ type: "approval.resolved", sequence: 3, payload: { approvalId: "app_1" } }),
    ];
    const spans = projectTraceSpans(events);
    const approvalSpan = spans.find((s) => s.kind === "approval");
    expect(approvalSpan).toBeDefined();
    expect(approvalSpan!.status).toBe("completed");
    expect(approvalSpan!.refs?.approvalId).toBe("app_1");
  });

  it("should produce workspace and artifact spans", () => {
    const events = [
      ev({ type: "run.created", sequence: 1 }),
      ev({ type: "workspace.file.created", sequence: 2, payload: { path: "/out.txt" } }),
      ev({ type: "artifact.created", sequence: 3, payload: { artifactId: "art_1" } }),
    ];
    const spans = projectTraceSpans(events);
    expect(spans.some((s) => s.kind === "workspace")).toBe(true);
    expect(spans.some((s) => s.kind === "artifact")).toBe(true);
  });

  it("should produce a completed model span from model.started + model.completed", () => {
    const events = [
      ev({ type: "run.created", sequence: 1 }),
      ev({ type: "model.started", sequence: 2 }),
      ev({ type: "model.completed", sequence: 3 }),
    ];
    const spans = projectTraceSpans(events);
    const modelSpan = spans.find((s) => s.kind === "model");
    expect(modelSpan).toBeDefined();
    expect(modelSpan!.status).toBe("completed");
    expect(modelSpan!.eventIds).toHaveLength(2);
  });

  it("should produce a failed model span from model.started + model.failed", () => {
    const events = [
      ev({ type: "run.created", sequence: 1 }),
      ev({ type: "model.started", sequence: 2 }),
      ev({ type: "model.failed", sequence: 3, payload: { error: { code: "MODEL_FAILED" } } }),
    ];
    const spans = projectTraceSpans(events);
    const modelSpan = spans.find((s) => s.kind === "model");
    expect(modelSpan).toBeDefined();
    expect(modelSpan!.status).toBe("failed");
  });

  it("should handle span duration calculation", () => {
    const events = [
      { ...ev({ type: "run.created", sequence: 1 }), timestamp: new Date("2025-01-01T00:00:00Z").toISOString() },
      { ...ev({ type: "run.completed", sequence: 2 }), timestamp: new Date("2025-01-01T00:01:00Z").toISOString() },
    ];
    const spans = projectTraceSpans(events);
    const runSpan = spans.find((s) => s.kind === "run")!;
    expect(runSpan.durationMs).toBe(60000);
  });
});
