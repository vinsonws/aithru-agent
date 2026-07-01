# Agent Run Limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add recoverable Agent Run limits for model requests, tool executions, token accounting, and repeated tool-call loops.

**Architecture:** Keep limits in the harness, derived from run mode plus event-log approvals. Reuse the existing approval pause/resume path for hard-limit continuation, and keep tool execution behind the Capability Router.

**Tech Stack:** TypeScript backend packages, Vitest, existing Agent event stream, existing approval store and routes.

## Global Constraints

- Agent remains an AI harness, not a workflow graph or workflow scheduler.
- Models may propose tool calls, but every real tool execution must continue through the Aithru Capability Router.
- `flash`, `thinking`, and `pro` share the same default limits: 50 model requests and 100 tool executions.
- `ultra` defaults to 100 model requests and 200 tool executions.
- Token limits are represented in policy shape, but no default hard token limit is enforced.
- Hard limits pause through approval instead of immediately failing the run.
- User denial of a limit-continuation approval ends the run as `failed` with `LIMIT_CONTINUATION_DENIED`.
- No new dependency, persistence table, workflow recursion model, per-tool quota system, or billing policy.
- Meaningful backend verification must run: `cd backend && npm run typecheck && npm run test && npm run check:no-python-backend && npm run examples:file-report`.

---

## File Structure

```txt
backend/packages/stream/src/events.ts
backend/packages/harness/src/run-limits.ts
backend/packages/harness/src/context-packet.ts
backend/packages/harness/src/model-turn.ts
backend/packages/harness/src/index.ts
backend/apps/api/src/approval-resolution.ts
backend/tests/harness/run-limits.test.ts
backend/tests/model/model-turn.test.ts
backend/tests/integration/api.test.ts
```

Responsibilities:

- `run-limits.ts`: one shared harness helper file for defaults, event-log counters, warning decisions, repeat hashing, and limit-continuation approval creation.
- `model-turn.ts`: checks model request limits before provider calls and tool/repeat limits before tool execution.
- `context-packet.ts`: includes recent `limit.warning` messages in model-only context.
- `approval-resolution.ts`: handles the special limit-continuation approval without requiring a pending tool-call record.
- Tests prove policy defaults, recoverable hard limits, tool counting, and repeat-call pausing.

---

### Task 1: Run Limit Policy Helpers

**Files:**

- Modify: `backend/packages/stream/src/events.ts`
- Create: `backend/packages/harness/src/run-limits.ts`
- Modify: `backend/packages/harness/src/index.ts`
- Test: `backend/tests/harness/run-limits.test.ts`

**Interfaces:**

- Produces: `EVENT_TYPES.LIMIT_WARNING = "limit.warning"`.
- Produces: `resolveRunLimits(run, events): AgentRunLimits`.
- Produces: `countModelRequests(events): number`.
- Produces: `countToolExecutions(events): number`.
- Produces: `countTokenUsage(events): { inputTokens: number; outputTokens: number; totalTokens: number }`.
- Produces: `pauseForLimitContinuation(args): AgentRun`.
- Produces: `repeatToolCallState(events, name, input): "ok" | "warn" | "pause"`.

- [ ] **Step 1: Write failing policy tests**

Create `backend/tests/harness/run-limits.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { AgentRun, AgentStreamEvent } from "@aithru-agent/contracts";
import {
  LIMIT_CONTINUATION_INCREMENT,
  LIMIT_CONTINUATION_TOOL,
  countModelRequests,
  countTokenUsage,
  countToolExecutions,
  repeatToolCallState,
  resolveRunLimits,
} from "@aithru-agent/harness";

function run(mode: "flash" | "thinking" | "pro" | "ultra" | null): AgentRun {
  return {
    id: `run_${mode ?? "none"}`,
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_1",
    task_msg: "test",
    scopes: ["*"],
    harness_options: mode ? ({ mode } as any) : null,
    status: "running",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
  };
}

function event(type: string, payload: unknown = {}): AgentStreamEvent {
  return {
    id: `evt_${Math.random()}`,
    run_id: "run_1",
    thread_id: null,
    sequence: 1,
    timestamp: "2026-01-01T00:00:00Z",
    type,
    source: { kind: "test" },
    visibility: "audit",
    redaction: "none",
    summary: null,
    payload,
  };
}

describe("run limits", () => {
  it("uses pro as the minimum budget for flash and thinking", () => {
    expect(resolveRunLimits(run("flash"), [])).toMatchObject({
      maxModelRequests: 50,
      maxToolExecutions: 100,
    });
    expect(resolveRunLimits(run("thinking"), [])).toEqual(resolveRunLimits(run("pro"), []));
    expect(resolveRunLimits(run("ultra"), [])).toMatchObject({
      maxModelRequests: 100,
      maxToolExecutions: 200,
    });
  });

  it("adds approved limit continuation increments from approval events", () => {
    const limits = resolveRunLimits(run("pro"), [
      event("approval.resolved", {
        name: LIMIT_CONTINUATION_TOOL,
        decision: "approved",
        limit_increment: LIMIT_CONTINUATION_INCREMENT,
      }),
    ]);

    expect(limits.maxModelRequests).toBe(75);
    expect(limits.maxToolExecutions).toBe(150);
  });

  it("counts model requests and tool executions from stream events", () => {
    expect(countModelRequests([
      event("context.packet.built"),
      event("context.packet.built"),
      event("tool.started"),
    ])).toBe(2);
    expect(countToolExecutions([
      event("tool.proposed"),
      event("tool.started"),
      event("tool.completed"),
    ])).toBe(1);
  });

  it("counts provider token usage when model usage events are present", () => {
    expect(countTokenUsage([
      event("model.usage", { input_tokens: 10, output_tokens: 4, total_tokens: 14 }),
      event("model.usage", { input_tokens: 3, output_tokens: 2 }),
    ])).toEqual({
      inputTokens: 13,
      outputTokens: 6,
      totalTokens: 19,
    });
  });

  it("detects repeated tool calls by canonical input", () => {
    const repeated = [
      event("tool.proposed", { name: "workspace.read_file", input: { b: 2, a: 1 } }),
      event("tool.proposed", { name: "workspace.read_file", input: { a: 1, b: 2 } }),
    ];

    expect(repeatToolCallState(repeated, "workspace.read_file", { a: 1, b: 2 })).toBe("warn");
    expect(repeatToolCallState([...repeated, ...repeated], "workspace.read_file", { b: 2, a: 1 })).toBe("pause");
  });
});
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd backend
npm run test -- tests/harness/run-limits.test.ts
```

Expected: fail because `run-limits.ts` exports and `EVENT_TYPES.LIMIT_WARNING` do not exist.

- [ ] **Step 3: Add the stream event constant**

In `backend/packages/stream/src/events.ts`, add:

```ts
  // Limits
  LIMIT_WARNING: "limit.warning",
```

- [ ] **Step 4: Add `run-limits.ts`**

Create `backend/packages/harness/src/run-limits.ts`:

```ts
import { nanoid } from "nanoid";
import type { AgentRun, AgentStreamEvent } from "@aithru-agent/contracts";
import { validateRunStatusTransition } from "@aithru-agent/contracts";
import type { AgentStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES, VISIBILITY } from "@aithru-agent/stream";

export type RunLimitKind = "model_requests" | "tool_executions" | "tokens" | "repeat_tool_call";

export type AgentRunLimits = {
  maxModelRequests: number;
  maxToolExecutions: number;
  maxInputTokens?: number;
  maxOutputTokens?: number;
  maxTotalTokens?: number;
};

export const LIMIT_CONTINUATION_TOOL = "agent.limit.continue";
export const LIMIT_CONTINUATION_INCREMENT = {
  maxModelRequests: 25,
  maxToolExecutions: 50,
} satisfies Pick<AgentRunLimits, "maxModelRequests" | "maxToolExecutions">;

export function resolveRunLimits(run: AgentRun, events: AgentStreamEvent[]): AgentRunLimits {
  const mode = modeOf(run);
  const limits: AgentRunLimits = mode === "ultra"
    ? { maxModelRequests: 100, maxToolExecutions: 200 }
    : { maxModelRequests: 50, maxToolExecutions: 100 };

  for (const event of events) {
    const payload = record(event.payload);
    if (
      event.type === EVENT_TYPES.APPROVAL_RESOLVED &&
      payload.name === LIMIT_CONTINUATION_TOOL &&
      payload.decision === "approved"
    ) {
      const increment = record(payload.limit_increment);
      limits.maxModelRequests += numberValue(increment.maxModelRequests);
      limits.maxToolExecutions += numberValue(increment.maxToolExecutions);
    }
  }
  return limits;
}

export function countModelRequests(events: AgentStreamEvent[]): number {
  return events.filter((event) => event.type === EVENT_TYPES.CONTEXT_PACKET_BUILT).length;
}

export function countToolExecutions(events: AgentStreamEvent[]): number {
  return events.filter((event) => event.type === EVENT_TYPES.TOOL_STARTED).length;
}

export function countTokenUsage(events: AgentStreamEvent[]): {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
} {
  return events.reduce(
    (total, event) => {
      if (event.type !== EVENT_TYPES.MODEL_USAGE) return total;
      const payload = record(event.payload);
      const inputTokens = numberValue(payload.input_tokens);
      const outputTokens = numberValue(payload.output_tokens);
      return {
        inputTokens: total.inputTokens + inputTokens,
        outputTokens: total.outputTokens + outputTokens,
        totalTokens: total.totalTokens + numberValue(payload.total_tokens || inputTokens + outputTokens),
      };
    },
    { inputTokens: 0, outputTokens: 0, totalTokens: 0 },
  );
}

export function shouldWarnAtLimit(kind: RunLimitKind, current: number, limit: number, events: AgentStreamEvent[]): boolean {
  if (limit <= 0 || current < Math.ceil(limit * 0.8)) return false;
  return !events.some((event) => event.type === EVENT_TYPES.LIMIT_WARNING && record(event.payload).kind === kind);
}

export function writeLimitWarning(args: {
  eventWriter: AgentEventWriter;
  run: AgentRun;
  kind: RunLimitKind;
  current: number;
  limit?: number;
  message: string;
}): AgentStreamEvent {
  return args.eventWriter.write(
    args.run.id,
    args.run.thread_id ?? null,
    EVENT_TYPES.LIMIT_WARNING,
    {
      kind: args.kind,
      current: args.current,
      limit: args.limit,
      message: args.message,
    },
    { visibility: VISIBILITY.USER, source: { kind: "harness" } },
  );
}

export function pauseForLimitContinuation(args: {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  run: AgentRun;
  kind: RunLimitKind;
  current: number;
  limit: number;
  message: string;
}): AgentRun {
  const approvalId = `aprv_limit_${nanoid(10)}`;
  const toolCallId = `limit:${args.kind}:${args.current}`;

  args.store.createApproval({
    id: approvalId,
    run_id: args.run.id,
    tool_call_id: toolCallId,
    tool_name: LIMIT_CONTINUATION_TOOL,
    status: "pending",
    created_at: nowIso(),
  });

  args.eventWriter.write(
    args.run.id,
    args.run.thread_id ?? null,
    EVENT_TYPES.APPROVAL_REQUESTED,
    {
      approval_id: approvalId,
      tool_call_id: toolCallId,
      name: LIMIT_CONTINUATION_TOOL,
      limit_kind: args.kind,
      current: args.current,
      limit: args.limit,
      limit_increment: LIMIT_CONTINUATION_INCREMENT,
      message: args.message,
    },
  );

  validateRunStatusTransition(args.run.status, "waiting_approval");
  const paused = args.store.updateRun(args.run.id, {
    status: "waiting_approval",
    current_approval_id: approvalId,
  });

  args.eventWriter.write(
    args.run.id,
    args.run.thread_id ?? null,
    EVENT_TYPES.RUN_PAUSED,
    {
      reason: "limit_reached",
      approval_id: approvalId,
      limit_kind: args.kind,
      current: args.current,
      limit: args.limit,
    },
  );

  return paused;
}

export function isLimitContinuationApproval(value: { tool_name: string }): boolean {
  return value.tool_name === LIMIT_CONTINUATION_TOOL;
}

export function limitKindFromToolCallId(toolCallId: string): RunLimitKind {
  const raw = toolCallId.split(":")[1];
  return raw === "tool_executions" || raw === "tokens" || raw === "repeat_tool_call"
    ? raw
    : "model_requests";
}

export function repeatToolCallState(
  events: AgentStreamEvent[],
  name: string,
  input: Record<string, unknown>,
): "ok" | "warn" | "pause" {
  const target = toolCallFingerprint(name, input);
  const previous = events.filter((event) => {
    const payload = record(event.payload);
    return event.type === EVENT_TYPES.TOOL_PROPOSED &&
      toolCallFingerprint(String(payload.name ?? ""), record(payload.input)) === target;
  }).length;
  const next = previous + 1;
  if (next >= 5) return "pause";
  if (next >= 3) return "warn";
  return "ok";
}

function modeOf(run: AgentRun): string {
  const options = record(run.harness_options);
  return typeof options.mode === "string" ? options.mode : "pro";
}

function toolCallFingerprint(name: string, input: Record<string, unknown>): string {
  return `${name}:${canonicalJson(input)}`;
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (!value || typeof value !== "object") return JSON.stringify(value);
  return `{${Object.entries(value as Record<string, unknown>)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, child]) => `${JSON.stringify(key)}:${canonicalJson(child)}`)
    .join(",")}}`;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}
```

- [ ] **Step 5: Export helpers**

In `backend/packages/harness/src/index.ts`, add:

```ts
export * from "./run-limits.js";
```

- [ ] **Step 6: Run the policy test**

Run:

```bash
cd backend
npm run test -- tests/harness/run-limits.test.ts
```

Expected: pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add backend/packages/stream/src/events.ts backend/packages/harness/src/run-limits.ts backend/packages/harness/src/index.ts backend/tests/harness/run-limits.test.ts
git commit -m "feat: add agent run limit policy"
```

---

### Task 2: Model Request Limit And Warnings

**Files:**

- Modify: `backend/packages/harness/src/model-turn.ts`
- Modify: `backend/packages/harness/src/context-packet.ts`
- Test: `backend/tests/model/model-turn.test.ts`

**Interfaces:**

- Consumes: `resolveRunLimits`, `countModelRequests`, `shouldWarnAtLimit`, `writeLimitWarning`, `pauseForLimitContinuation`.
- Produces: model request hard limit pauses with `approval.requested` + `run.paused`.
- Produces: recent `limit.warning` lines in model context.

- [ ] **Step 1: Add failing tests for model request limits**

Append these tests to `backend/tests/model/model-turn.test.ts`:

```ts
  it("uses the pro model request limit for flash and thinking modes", async () => {
    for (const mode of ["flash", "thinking", "pro"] as const) {
      const store = new InMemoryStore();
      const eventWriter = new AgentEventWriter(store);
      const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
      const run = { ...createRun(), id: `run_limit_${mode}`, harness_options: { mode } as any };
      store.createRun(run);

      const toolTurns = Array.from({ length: 20 }, (_, index) => [
        {
          type: "tool_call" as const,
          id: `tc_${mode}_${index}`,
          name: "workspace.list_files",
          input: {},
        },
        { type: "completed" as const },
      ]);

      const completed = await new ModelTurnLoop({
        store,
        eventWriter,
        capabilityRouter,
        modelAdapter: new TestModelAdapter([
          ...toolTurns,
          [{ type: "text_delta", delta: "done" }, { type: "completed" }],
        ]),
      }).execute(run);

      expect(completed.status).toBe("completed");
      expect(store.listEvents(run.id).filter((event) => event.type === "context.packet.built")).toHaveLength(21);
    }
  });

  it("pauses for approval instead of failing when the model request limit is reached", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_model_limit", harness_options: { mode: "pro" } as any };
    store.createRun(run);

    for (let index = 0; index < 50; index += 1) {
      eventWriter.write(run.id, null, "context.packet.built", {});
    }

    const paused = await new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([[{ type: "text_delta", delta: "should not run" }, { type: "completed" }]]),
    }).execute(run);

    expect(paused.status).toBe("waiting_approval");
    expect(paused.current_approval_id).toBeTruthy();
    expect(store.listEvents(run.id).map((event) => event.type)).toContain("approval.requested");
    expect(store.listEvents(run.id).map((event) => event.type)).toContain("run.paused");
    expect(store.listEvents(run.id).map((event) => event.type)).not.toContain("run.failed");
  });

  it("adds limit warnings to the next model context packet", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_limit_context", harness_options: { mode: "pro" } as any };
    store.createRun(run);

    eventWriter.write(run.id, null, "limit.warning", {
      kind: "repeat_tool_call",
      current: 3,
      message: "Repeated tool call detected.",
    });

    await new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        (input) => {
          expect(input.messages[0].content).toContain("Run warnings:");
          expect(input.messages[0].content).toContain("Repeated tool call detected.");
          return [{ type: "text_delta", delta: "ok" }, { type: "completed" }];
        },
      ]),
    }).execute(run);
  });
```

- [ ] **Step 2: Run the failing model tests**

Run:

```bash
cd backend
npm run test -- tests/model/model-turn.test.ts
```

Expected: the hard-limit test fails because the current loop ignores previous model request count, and the context warning test fails because context packets ignore `limit.warning`.

- [ ] **Step 3: Add limit warnings to context packets**

In `backend/packages/harness/src/context-packet.ts`, after `toolLines`, add:

```ts
  const warningLines = args.events
    .filter((event) => event.type === "limit.warning")
    .slice(-3)
    .map((event) => {
      const payload = event.payload as Record<string, unknown>;
      return `- ${String(payload.kind ?? "limit")}: ${String(payload.message ?? "Run limit warning.")}`;
    });
```

Before the summary context part, add:

```ts
  if (warningLines.length) contextParts.push(`Run warnings:\n${warningLines.join("\n")}`);
```

- [ ] **Step 4: Replace the fixed default turn ceiling**

In `backend/packages/harness/src/model-turn.ts`, import:

```ts
import {
  countModelRequests,
  pauseForLimitContinuation,
  resolveRunLimits,
  shouldWarnAtLimit,
  writeLimitWarning,
} from "./run-limits.js";
```

Replace:

```ts
    const maxTurns = this.deps.maxTurns ?? DEFAULT_MAX_MODEL_TURNS;

    for (let turn = 0; turn < maxTurns; turn += 1) {
```

with:

```ts
    for (;;) {
```

At the start of the loop body, after `const runEvents = this.deps.store.listEvents(run.id);`, add:

```ts
      const limits = resolveRunLimits(currentRun, runEvents);
      const priorModelRequests = countModelRequests(runEvents);
      const maxModelRequests = this.deps.maxTurns ?? limits.maxModelRequests;

      if (priorModelRequests >= maxModelRequests) {
        loop.emitMessageCompleted(messageId, content);
        return pauseForLimitContinuation({
          store: this.deps.store,
          eventWriter: this.deps.eventWriter,
          run: currentRun,
          kind: "model_requests",
          current: priorModelRequests,
          limit: maxModelRequests,
          message: "The run reached its model request limit.",
        });
      }

      const nextModelRequest = priorModelRequests + 1;
      if (shouldWarnAtLimit("model_requests", nextModelRequest, maxModelRequests, runEvents)) {
        writeLimitWarning({
          eventWriter: this.deps.eventWriter,
          run: currentRun,
          kind: "model_requests",
          current: nextModelRequest,
          limit: maxModelRequests,
          message: "The run is close to its model request limit.",
        });
      }
```

Change the `turnIndex` passed to the model:

```ts
        turnIndex: priorModelRequests,
```

Remove the bottom `MODEL_TURN_LIMIT_EXCEEDED` block and remove `DEFAULT_MAX_MODEL_TURNS`.

- [ ] **Step 5: Run the model tests**

Run:

```bash
cd backend
npm run test -- tests/model/model-turn.test.ts
```

Expected: pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/packages/harness/src/model-turn.ts backend/packages/harness/src/context-packet.ts backend/tests/model/model-turn.test.ts
git commit -m "feat: pause model runs at request limits"
```

---

### Task 3: Tool Execution Limit And Repeat Detection

**Files:**

- Modify: `backend/packages/harness/src/model-turn.ts`
- Test: `backend/tests/model/model-turn.test.ts`

**Interfaces:**

- Consumes: `countToolExecutions`, `repeatToolCallState`, `shouldWarnAtLimit`, `writeLimitWarning`, `pauseForLimitContinuation`.
- Produces: tool hard limits pause before `tool.proposed` and `tool.started`.
- Produces: repeated identical tool proposals warn at the third proposal and pause at the fifth.

- [ ] **Step 1: Add failing tests**

Append these tests to `backend/tests/model/model-turn.test.ts`:

```ts
  it("pauses before executing a tool when the tool execution limit is reached", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_tool_limit", harness_options: { mode: "pro" } as any };
    store.createRun(run);

    for (let index = 0; index < 100; index += 1) {
      eventWriter.write(run.id, null, "tool.started", { tool_call_id: `old_${index}`, name: "workspace.list_files" });
    }

    const paused = await new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          { type: "tool_call", id: "tc_over", name: "workspace.list_files", input: {} },
          { type: "completed" },
        ],
      ]),
    }).execute(run);

    expect(paused.status).toBe("waiting_approval");
    expect(store.listEvents(run.id).filter((event) => event.type === "tool.proposed")).toHaveLength(0);
    expect(store.listEvents(run.id).filter((event) => event.type === "tool.started")).toHaveLength(100);
  });

  it("warns and then pauses repeated identical tool calls", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_repeat_tool", harness_options: { mode: "pro" } as any };
    store.createRun(run);

    const repeatedCall = { name: "workspace.list_files", input: {} };
    for (let index = 0; index < 4; index += 1) {
      eventWriter.write(run.id, null, "tool.proposed", {
        tool_call_id: `old_${index}`,
        ...repeatedCall,
      });
    }

    const paused = await new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          { type: "tool_call", id: "tc_repeat", ...repeatedCall },
          { type: "completed" },
        ],
      ]),
    }).execute(run);

    expect(paused.status).toBe("waiting_approval");
    const warning = store.listEvents(run.id).find((event) => event.type === "limit.warning");
    expect(warning?.payload).toMatchObject({
      kind: "repeat_tool_call",
      current: 5,
    });
    expect(store.listEvents(run.id).filter((event) => event.type === "tool.started")).toHaveLength(0);
  });
```

- [ ] **Step 2: Run the failing model tests**

Run:

```bash
cd backend
npm run test -- tests/model/model-turn.test.ts
```

Expected: fail because tool-call limit checks are not wired.

- [ ] **Step 3: Check tool limits before executing the proposed tool**

In `backend/packages/harness/src/model-turn.ts`, extend the existing `./run-limits.js` import:

```ts
  countToolExecutions,
  repeatToolCallState,
```

Inside the `event.type === "tool_call"` branch, before `sawToolCall = true`, add:

```ts
          const latestRun = this.deps.store.getRun(run.id) ?? currentRun;
          const latestEvents = this.deps.store.listEvents(run.id);
          const latestLimits = resolveRunLimits(latestRun, latestEvents);
          const priorToolExecutions = countToolExecutions(latestEvents);
          const nextToolExecution = priorToolExecutions + 1;
          const repeatState = repeatToolCallState(latestEvents, event.name, event.input);

          if (shouldWarnAtLimit("tool_executions", nextToolExecution, latestLimits.maxToolExecutions, latestEvents)) {
            writeLimitWarning({
              eventWriter: this.deps.eventWriter,
              run: latestRun,
              kind: "tool_executions",
              current: nextToolExecution,
              limit: latestLimits.maxToolExecutions,
              message: "The run is close to its tool execution limit.",
            });
          }

          if (repeatState === "warn" || repeatState === "pause") {
            writeLimitWarning({
              eventWriter: this.deps.eventWriter,
              run: latestRun,
              kind: "repeat_tool_call",
              current: repeatState === "pause" ? 5 : 3,
              message: `The model repeated ${event.name} with the same input.`,
            });
          }

          if (priorToolExecutions >= latestLimits.maxToolExecutions) {
            flushToolInputDelta();
            loop.emitMessageCompleted(messageId, content);
            return pauseForLimitContinuation({
              store: this.deps.store,
              eventWriter: this.deps.eventWriter,
              run: latestRun,
              kind: "tool_executions",
              current: priorToolExecutions,
              limit: latestLimits.maxToolExecutions,
              message: "The run reached its tool execution limit.",
            });
          }

          if (repeatState === "pause") {
            flushToolInputDelta();
            loop.emitMessageCompleted(messageId, content);
            return pauseForLimitContinuation({
              store: this.deps.store,
              eventWriter: this.deps.eventWriter,
              run: latestRun,
              kind: "repeat_tool_call",
              current: 5,
              limit: 5,
              message: `The model repeated ${event.name} with the same input five times.`,
            });
          }
```

Keep the existing `sawToolCall = true; const call = await loop.executeToolCall(...)` after this block.

- [ ] **Step 4: Run the model tests**

Run:

```bash
cd backend
npm run test -- tests/model/model-turn.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/packages/harness/src/model-turn.ts backend/tests/model/model-turn.test.ts
git commit -m "feat: guard tool execution limits"
```

---

### Task 4: Resolve Limit Continuation Approvals

**Files:**

- Modify: `backend/apps/api/src/approval-resolution.ts`
- Test: `backend/tests/integration/api.test.ts`

**Interfaces:**

- Consumes: `isLimitContinuationApproval`, `limitKindFromToolCallId`, `LIMIT_CONTINUATION_INCREMENT`, `LIMIT_CONTINUATION_TOOL`.
- Produces: approved limit continuation writes `approval.resolved`, `run.resumed`, queues the run, and increases limits via the event log.
- Produces: denied limit continuation writes `approval.resolved`, `run.failed`, and stores `LIMIT_CONTINUATION_DENIED`.

- [ ] **Step 1: Add failing API integration tests**

Append these tests to `backend/tests/integration/api.test.ts`:

```ts
  it("POST /api/approvals/:id/resolve resumes approved limit continuation approvals", async () => {
    const runtime = getRuntime();
    const approvalId = "aprv_limit_resume";
    const run: AgentRun = {
      id: "run_api_limit_resume",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "chat",
      thread_id: null,
      workspace_id: "ws_api_limit_resume",
      task_msg: "Continue after limit",
      scopes: ["*"],
      harness_options: { model_profile_key: "default", mode: "pro" } as any,
      status: "waiting_approval",
      current_approval_id: approvalId,
      started_at: testNow(),
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    };
    runtime.store.createRun(run);
    runtime.store.createApproval({
      id: approvalId,
      run_id: run.id,
      tool_call_id: "limit:model_requests:50",
      tool_name: "agent.limit.continue",
      status: "pending",
      created_at: testNow(),
    });

    const res = await app.inject({
      method: "POST",
      url: `/api/approvals/${approvalId}/resolve`,
      payload: { decision: "approved" },
    });

    for (let attempt = 0; attempt < 20 && runtime.store.getRun(run.id)?.status !== "completed"; attempt += 1) {
      await wait(10);
    }

    expect(res.statusCode).toBe(200);
    expect(runtime.store.getRun(run.id)?.status).toBe("completed");
    expect(runtime.store.listEvents(run.id).map((event) => event.type)).toEqual(
      expect.arrayContaining([
        EVENT_TYPES.APPROVAL_RESOLVED,
        EVENT_TYPES.RUN_RESUMED,
        EVENT_TYPES.RUN_COMPLETED,
      ]),
    );
    expect(runtime.store.listEvents(run.id).find((event) => event.type === EVENT_TYPES.APPROVAL_RESOLVED)?.payload)
      .toMatchObject({
        name: "agent.limit.continue",
        decision: "approved",
        limit_kind: "model_requests",
        limit_increment: { maxModelRequests: 25, maxToolExecutions: 50 },
      });
  });

  it("POST /api/approvals/:id/resolve fails denied limit continuation approvals", async () => {
    const runtime = getRuntime();
    const approvalId = "aprv_limit_deny";
    const run: AgentRun = {
      id: "run_api_limit_deny",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "chat",
      thread_id: null,
      workspace_id: "ws_api_limit_deny",
      task_msg: "Stop after limit",
      scopes: ["*"],
      harness_options: { model_profile_key: "default", mode: "pro" } as any,
      status: "waiting_approval",
      current_approval_id: approvalId,
      started_at: testNow(),
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    };
    runtime.store.createRun(run);
    runtime.store.createApproval({
      id: approvalId,
      run_id: run.id,
      tool_call_id: "limit:tool_executions:100",
      tool_name: "agent.limit.continue",
      status: "pending",
      created_at: testNow(),
    });

    const res = await app.inject({
      method: "POST",
      url: `/api/approvals/${approvalId}/resolve`,
      payload: { decision: "rejected" },
    });

    expect(res.statusCode).toBe(200);
    expect(runtime.store.getRun(run.id)?.status).toBe("failed");
    expect(runtime.store.getRun(run.id)?.error).toMatchObject({
      code: "LIMIT_CONTINUATION_DENIED",
    });
    expect(runtime.store.listEvents(run.id).map((event) => event.type)).toEqual(
      expect.arrayContaining([EVENT_TYPES.APPROVAL_RESOLVED, EVENT_TYPES.RUN_FAILED]),
    );
  });
```

- [ ] **Step 2: Run the failing API tests**

Run:

```bash
cd backend
npm run test -- tests/integration/api.test.ts
```

Expected: fail because the resolver expects a pending tool-call record for every approval.

- [ ] **Step 3: Add the limit approval branch**

In `backend/apps/api/src/approval-resolution.ts`, extend the harness imports:

```ts
  LIMIT_CONTINUATION_INCREMENT,
  isLimitContinuationApproval,
  limitKindFromToolCallId,
```

Inside the resolver, replace the `toolCall` setup with:

```ts
    const limitApproval = isLimitContinuationApproval(pendingApproval);
    const toolCall = shouldResume && !limitApproval
      ? ensureToolCallRecordForApproval(deps.store, pendingApproval)
      : null;
    if (shouldResume && !limitApproval && !toolCall) {
      throw new ApprovalResolutionError("PENDING_TOOL_CALL_NOT_FOUND");
    }
```

In the `APPROVAL_RESOLVED` payload, add limit metadata:

```ts
          ...(limitApproval
            ? {
                limit_kind: limitKindFromToolCallId(approval.tool_call_id),
                limit_increment: LIMIT_CONTINUATION_INCREMENT,
              }
            : {}),
```

Replace the existing early return:

```ts
    if (!shouldResume || !toolCall || !wasPending) return approval;
```

with:

```ts
    if (!shouldResume || !wasPending) return approval;

    if (limitApproval) {
      return resolveLimitContinuationApproval(deps, run, approval, decision);
    }

    if (!toolCall) throw new ApprovalResolutionError("PENDING_TOOL_CALL_NOT_FOUND");
```

Add this helper near `executeApprovedToolCall`:

```ts
async function resolveLimitContinuationApproval(
  deps: {
    store: AgentStore;
    eventWriter: AgentEventWriter;
    scheduleRunExecution: ScheduleRunExecution;
  },
  run: AgentRun,
  approval: AgentApproval,
  decision: "approved" | "denied",
): Promise<AgentApproval> {
  if (decision === "denied") {
    const failed = deps.store.updateRun(run.id, {
      status: "failed",
      current_approval_id: null,
      completed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      error: {
        code: "LIMIT_CONTINUATION_DENIED",
        message: "User denied continuing after the run limit was reached.",
      },
    });
    deps.eventWriter.write(run.id, run.thread_id ?? null, EVENT_TYPES.RUN_FAILED, {
      error: failed.error,
    });
    return approval;
  }

  deps.store.updateRun(run.id, {
    status: "running",
    current_approval_id: null,
  });
  deps.eventWriter.write(
    run.id,
    run.thread_id ?? null,
    EVENT_TYPES.RUN_RESUMED,
    { status: "running", resume_reason: "limit_continuation_approved", approval_id: approval.id },
  );

  void deps.scheduleRunExecution(deps.store.updateRun(run.id, { status: "queued" }));
  return approval;
}
```

- [ ] **Step 4: Run the API tests**

Run:

```bash
cd backend
npm run test -- tests/integration/api.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/apps/api/src/approval-resolution.ts backend/tests/integration/api.test.ts
git commit -m "feat: resume runs after limit approval"
```

---

### Task 5: Final Backend Verification

**Files:**

- No planned source changes.

**Interfaces:**

- Confirms the Agent Harness backend remains TypeScript-only and the file report example still works.

- [ ] **Step 1: Run package typecheck**

```bash
cd backend
npm run typecheck
```

Expected: exit code 0.

- [ ] **Step 2: Run the full test suite**

```bash
cd backend
npm run test
```

Expected: exit code 0.

- [ ] **Step 3: Run the no-Python backend guard**

```bash
cd backend
npm run check:no-python-backend
```

Expected: exit code 0.

- [ ] **Step 4: Run the file report example**

```bash
cd backend
npm run examples:file-report
```

Expected: exit code 0.

- [ ] **Step 5: Inspect final diff**

```bash
git status --short
git diff --stat HEAD
```

Expected: only intended backend files are modified.

- [ ] **Step 6: Commit verification fixes only if needed**

If verification reveals a real issue, make the smallest backend fix, rerun the failing command, and commit with:

```bash
git add backend
git commit -m "fix: stabilize agent run limits"
```
