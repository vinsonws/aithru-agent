import { describe, expect, it } from "vitest";
import type { AgentRun, AgentStreamEvent } from "@aithru-agent/contracts";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import {
  resolveRunLimits,
  countModelRequests,
  countToolExecutions,
  countTokenUsage,
  shouldWarnAtLimit,
  writeLimitWarning,
  pauseForLimitContinuation,
  isLimitContinuationApproval,
  limitKindFromToolCallId,
  repeatToolCallState,
  LIMIT_CONTINUATION_TOOL,
  LIMIT_CONTINUATION_INCREMENT,
} from "@aithru-agent/harness";

function createRun(mode?: string): AgentRun {
  return {
    id: "run_limits_test",
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_limits_test",
    task_msg: "test",
    scopes: ["*"],
    harness_options: mode ? { mode } as unknown as Record<string, unknown> : null,
    status: "queued",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
  };
}

function makeEvent(type: string, payload: Record<string, unknown>): AgentStreamEvent {
  return {
    id: `evt_${Math.random().toString(36).slice(2, 8)}`,
    run_id: "run_limits_test",
    thread_id: null,
    sequence: 1,
    timestamp: "2026-01-01T00:00:00Z",
    type,
    source: { kind: "system" },
    visibility: "audit",
    redaction: "none",
    summary: null,
    payload,
  };
}

describe("RunLimits", () => {
  it("returns default limits by mode: flash=thinking=pro=50/100, ultra=100/200", () => {
    const empty: AgentStreamEvent[] = [];
    expect(resolveRunLimits(createRun("flash"), empty)).toEqual({ maxModelRequests: 50, maxToolExecutions: 100 });
    expect(resolveRunLimits(createRun("thinking"), empty)).toEqual({ maxModelRequests: 50, maxToolExecutions: 100 });
    expect(resolveRunLimits(createRun("pro"), empty)).toEqual({ maxModelRequests: 50, maxToolExecutions: 100 });
    expect(resolveRunLimits(createRun("ultra"), empty)).toEqual({ maxModelRequests: 100, maxToolExecutions: 200 });
  });

  it("uses explicit run limit overrides from harness options", () => {
    const run = {
      ...createRun("ultra"),
      harness_options: {
        mode: "ultra",
        max_model_requests: 15,
        max_tool_executions: 30,
      } as unknown as Record<string, unknown>,
    };
    expect(resolveRunLimits(run, [])).toEqual({ maxModelRequests: 15, maxToolExecutions: 30 });
  });

  it("adds limit increments from approved limit continuation approvals", () => {
    const empty: AgentStreamEvent[] = [];
    const run = createRun("pro");
    const approved = makeEvent(EVENT_TYPES.APPROVAL_RESOLVED, {
      approval_id: "aprv_1",
      tool_call_id: "limit:model_requests:1",
      name: LIMIT_CONTINUATION_TOOL,
      decision: "approved",
    });
    const denied = makeEvent(EVENT_TYPES.APPROVAL_RESOLVED, {
      approval_id: "aprv_2",
      tool_call_id: "limit:tool_executions:1",
      name: LIMIT_CONTINUATION_TOOL,
      decision: "denied",
    });
    const lines = resolveRunLimits(run, [approved]);
    expect(lines.maxModelRequests).toBe(50 + LIMIT_CONTINUATION_INCREMENT.maxModelRequests);
    expect(lines.maxToolExecutions).toBe(100 + LIMIT_CONTINUATION_INCREMENT.maxToolExecutions);
    const withDenied = resolveRunLimits(run, [approved, denied]);
    expect(withDenied.maxModelRequests).toBe(50 + LIMIT_CONTINUATION_INCREMENT.maxModelRequests);
  });

  it("counts model requests, tool executions, and token usage from events", () => {
    const events = [
      makeEvent(EVENT_TYPES.CONTEXT_PACKET_BUILT, { total_messages: 1 }),
      makeEvent(EVENT_TYPES.TOOL_STARTED, { tool_call_id: "tc_1", name: "workspace.read_file" }),
      makeEvent(EVENT_TYPES.CONTEXT_PACKET_BUILT, { total_messages: 2 }),
      makeEvent(EVENT_TYPES.MODEL_USAGE, { requests: 1, input_tokens: 10, output_tokens: 20, total_tokens: 30 }),
      makeEvent(EVENT_TYPES.TOOL_STARTED, { tool_call_id: "tc_2", name: "workspace.write_file" }),
      makeEvent(EVENT_TYPES.MODEL_USAGE, { requests: 1, input_tokens: 5, output_tokens: 15, total_tokens: 20 }),
    ];
    expect(countModelRequests(events)).toBe(2);
    expect(countToolExecutions(events)).toBe(2);
    expect(countTokenUsage(events)).toEqual({ input_tokens: 15, output_tokens: 35, total_tokens: 50 });
  });

  it("detects repeated tool calls: warns at 3, pauses at 5", () => {
    const name = "workspace.write_file";
    const input = { path: "/f.txt", content: "x" };
    const events: AgentStreamEvent[] = [];
    events.push(makeEvent(EVENT_TYPES.TOOL_PROPOSED, { tool_call_id: "tc_0", name, input }));
    events.push(makeEvent(EVENT_TYPES.TOOL_PROPOSED, { tool_call_id: "tc_1", name, input }));
    expect(repeatToolCallState(events, name, input)).toBe("warn");
    events.push(makeEvent(EVENT_TYPES.TOOL_PROPOSED, { tool_call_id: "tc_2", name, input }));
    events.push(makeEvent(EVENT_TYPES.TOOL_PROPOSED, { tool_call_id: "tc_3", name, input }));
    expect(repeatToolCallState(events, name, input)).toBe("pause");
    const differentInput = { path: "/other.txt", content: "y" };
    expect(repeatToolCallState(events, name, differentInput)).toBe("ok");
  });

  it("shouldWarnAtLimit returns true at 80%+ and no prior warning for same kind", () => {
    const empty: AgentStreamEvent[] = [];
    expect(shouldWarnAtLimit("model_requests", 40, 50, empty)).toBe(true);
    expect(shouldWarnAtLimit("model_requests", 39, 50, empty)).toBe(false);
    const warned = [makeEvent(EVENT_TYPES.LIMIT_WARNING, { kind: "model_requests", current: 40, limit: 50 })];
    expect(shouldWarnAtLimit("model_requests", 45, 50, warned)).toBe(false);
    expect(shouldWarnAtLimit("tool_executions", 85, 100, warned)).toBe(true);
  });

  it("pauseForLimitContinuation creates approval and pauses the run", () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const run = { ...createRun("pro"), status: "running" as const };
    store.createRun(run);

    const result = pauseForLimitContinuation({
      store, eventWriter, run,
      kind: "model_requests", current: 50, limit: 50,
      message: "Model request limit reached",
    });

    expect(result.status).toBe("waiting_approval");
    expect(result.current_approval_id).toBeTruthy();
    const approvals = store.listApprovals({ run_id: run.id });
    expect(approvals).toHaveLength(1);
    expect(approvals[0].tool_name).toBe(LIMIT_CONTINUATION_TOOL);
    expect(store.listEvents(run.id).some((e) => e.type === EVENT_TYPES.APPROVAL_REQUESTED)).toBe(true);
    expect(store.listEvents(run.id).some((e) => e.type === EVENT_TYPES.RUN_PAUSED)).toBe(true);
  });

  it("isLimitContinuationApproval and limitKindFromToolCallId work", () => {
    expect(isLimitContinuationApproval({ tool_name: LIMIT_CONTINUATION_TOOL })).toBe(true);
    expect(isLimitContinuationApproval({ tool_name: "workspace.read_file" })).toBe(false);
    expect(limitKindFromToolCallId("limit:model_requests:1")).toBe("model_requests");
    expect(limitKindFromToolCallId("limit:tool_executions:3")).toBe("tool_executions");
    expect(limitKindFromToolCallId("tc_normal")).toBeNull();
  });

  it("writeLimitWarning writes a limit.warning event", () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const run = createRun("pro");
    store.createRun(run);

    writeLimitWarning({
      eventWriter, run,
      kind: "model_requests", current: 40, limit: 50,
      message: "Approaching model request limit",
    });

    const events = store.listEvents(run.id);
    const warning = events.find((e) => e.type === EVENT_TYPES.LIMIT_WARNING);
    expect(warning).toBeDefined();
    const payload = warning!.payload as Record<string, unknown>;
    expect(payload.kind).toBe("model_requests");
    expect(payload.current).toBe(40);
    expect(payload.limit).toBe(50);
  });
});
