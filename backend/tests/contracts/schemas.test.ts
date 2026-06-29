import { describe, it, expect } from "vitest";
import { Value } from "@sinclair/typebox/value";
import {
  AgentThreadSchema,
  AgentMessageSchema,
  AgentRunSchema,
  AgentStreamEventSchema,
  validateRunStatusTransition,
  TERMINAL_RUN_STATUSES,
} from "@aithru-agent/contracts";

describe("AgentThreadSchema", () => {
  it("validates a valid thread", () => {
    const thread = {
      id: "thread_1",
      org_id: "org_1",
      owner_user_id: "user_1",
      title: "Test Thread",
      status: "active",
      created_at: "2026-06-29T00:00:00Z",
      updated_at: "2026-06-29T00:00:00Z",
    };
    const errors = [...Value.Errors(AgentThreadSchema, thread)];
    expect(errors).toHaveLength(0);
  });

  it("accepts null title", () => {
    const thread = {
      id: "thread_1",
      org_id: "org_1",
      owner_user_id: "user_1",
      title: null,
      status: "active",
      created_at: "2026-06-29T00:00:00Z",
      updated_at: "2026-06-29T00:00:00Z",
    };
    const errors = [...Value.Errors(AgentThreadSchema, thread)];
    expect(errors).toHaveLength(0);
  });
});

describe("AgentMessageSchema", () => {
  it("validates a user message", () => {
    const msg = {
      id: "msg_1",
      thread_id: "thread_1",
      role: "user",
      content: "Hello",
      run_id: null,
      workspace_paths: [],
      created_at: "2026-06-29T00:00:00Z",
    };
    const errors = [...Value.Errors(AgentMessageSchema, msg)];
    expect(errors).toHaveLength(0);
  });

  it("validates an assistant message", () => {
    const msg = {
      id: "msg_1",
      thread_id: "thread_1",
      role: "assistant",
      content: "Hi there!",
      run_id: "run_1",
      workspace_paths: ["/reports/report.md"],
      created_at: "2026-06-29T00:00:00Z",
    };
    const errors = [...Value.Errors(AgentMessageSchema, msg)];
    expect(errors).toHaveLength(0);
  });
});

describe("AgentRunSchema", () => {
  it("validates a queued run", () => {
    const run = {
      id: "run_1",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "chat",
      thread_id: "thread_1",
      workspace_id: "ws_1",
      task_msg: "Do something",
      scopes: ["*"],
      harness_options: null,
      status: "queued",
      started_at: "2026-06-29T00:00:00Z",
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    };
    const errors = [...Value.Errors(AgentRunSchema, run)];
    expect(errors).toHaveLength(0);
  });
});

describe("AgentStreamEventSchema", () => {
  it("validates a stream event", () => {
    const event = {
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
    const errors = [...Value.Errors(AgentStreamEventSchema, event)];
    expect(errors).toHaveLength(0);
  });

  it("validates event with null thread_id", () => {
    const event = {
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
    const errors = [...Value.Errors(AgentStreamEventSchema, event)];
    expect(errors).toHaveLength(0);
  });
});

describe("validateRunStatusTransition", () => {
  it("allows queued -> running", () => {
    expect(validateRunStatusTransition("queued", "running")).toBe("running");
  });

  it("allows queued -> cancelled", () => {
    expect(validateRunStatusTransition("queued", "cancelled")).toBe("cancelled");
  });

  it("allows running -> completed", () => {
    expect(validateRunStatusTransition("running", "completed")).toBe("completed");
  });

  it("allows running -> waiting_approval", () => {
    expect(validateRunStatusTransition("running", "waiting_approval")).toBe("waiting_approval");
  });

  it("rejects completed -> running (terminal)", () => {
    expect(() => validateRunStatusTransition("completed", "running")).toThrow(
      "Cannot transition terminal run",
    );
  });

  it("rejects failed -> running (terminal)", () => {
    expect(() => validateRunStatusTransition("failed", "running")).toThrow(
      "Cannot transition terminal run",
    );
  });

  it("rejects queued -> completed (invalid transition)", () => {
    expect(() => validateRunStatusTransition("queued", "completed")).toThrow(
      "Invalid run status transition",
    );
  });

  it("allows same status (no-op)", () => {
    expect(validateRunStatusTransition("running", "running")).toBe("running");
  });
});

describe("TERMINAL_RUN_STATUSES", () => {
  it("contains completed, failed, cancelled", () => {
    expect(TERMINAL_RUN_STATUSES.has("completed")).toBe(true);
    expect(TERMINAL_RUN_STATUSES.has("failed")).toBe(true);
    expect(TERMINAL_RUN_STATUSES.has("cancelled")).toBe(true);
  });
});
