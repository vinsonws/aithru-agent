# Agent Run Limits Design

Date: 2026-07-01
Status: approved design

## Problem

Agent runs need guardrails so a model cannot loop forever, spend unbounded
tokens, or execute unbounded tools. The current fixed model turn ceiling caught
real loops, but it also failed legitimate multi-step skill runs too early.

The limit model should be generic enough for approvals, skills, tools, and
future subagents without becoming an Agent workflow system.

## Decision

Add an Aithru-owned run limit policy with three counters:

- model request count;
- executed tool call count;
- provider token usage.

The model request limit and tool execution limit use `pro` as the minimum
budget. `flash` and `thinking` get the same limits as `pro`; limits are safety
guardrails, not product-tier throttles.

Suggested defaults:

| Mode | Model requests | Tool executions |
| --- | ---: | ---: |
| flash | 50 | 100 |
| thinking | 50 | 100 |
| pro | 50 | 100 |
| ultra | 100 | 200 |

Token limits are supported in policy shape but have no default hard limit until
real provider usage data justifies one.

## Non-Goals

- No Agent workflow graph or recursion semantics.
- No per-tool quota system in the first implementation.
- No pricing or billing policy.
- No hard token defaults before usage data exists.
- No model-mode downgrades based on limits.

## References

DeerFlow uses LangGraph recursion limits and subagent turn limits. Public issue
discussion shows defaults such as a main recursion limit and separate subagent
`max_turns`, with failures when complex runs exceed them.

Pydantic AI separates limits into model request count, tool call count, and
token usage limits. Its default request limit is generous, while tool and token
limits can be configured independently.

Aithru should follow the same separation, but expose it as harness run state and
approval-driven recovery rather than graph recursion.

## Policy Shape

Minimum TypeScript shape:

```ts
type AgentRunLimits = {
  maxModelRequests: number;
  maxToolExecutions: number;
  maxInputTokens?: number;
  maxOutputTokens?: number;
  maxTotalTokens?: number;
};
```

Mode defaults live in harness policy code:

```ts
const RUN_LIMITS_BY_MODE = {
  flash: { maxModelRequests: 50, maxToolExecutions: 100 },
  thinking: { maxModelRequests: 50, maxToolExecutions: 100 },
  pro: { maxModelRequests: 50, maxToolExecutions: 100 },
  ultra: { maxModelRequests: 100, maxToolExecutions: 200 },
};
```

Run-specific overrides are outside the first implementation. Add them through
existing harness options only after a real caller needs them.

## Counting Rules

Model requests count each provider request started by the model turn loop.

Tool executions count only real executions routed through the Capability
Router. Proposed tool calls that pause for approval do not count until they are
approved and started.

Token usage accumulates from provider usage events when available. Missing token
usage does not fail a run.

## Limit Behavior

At 80% of a model or tool limit, emit a warning event that the UI can surface.

At the hard limit, pause the run and request approval to continue with a small
increment:

- `approval.requested`
- `run.paused`
- user approval resumes with an increased limit
- user denial ends the run as `failed` with `LIMIT_CONTINUATION_DENIED`

This keeps long legitimate tasks recoverable without silently increasing every
run's budget.

## Loop Detection

Track repeated tool calls by hashing:

```txt
tool name + canonical JSON input
```

If the same call repeats three times in one run, emit a warning into the next
model context packet. If it repeats five times, pause and ask the user whether
to continue.

This is intentionally simple. It catches obvious retry loops without adding a
planner, graph engine, or semantic loop detector.

## Event Contract

Add one generic warning event:

```ts
limit.warning
```

Payload:

```ts
type LimitWarningPayload = {
  kind: "model_requests" | "tool_executions" | "tokens" | "repeat_tool_call";
  current: number;
  limit?: number;
  message: string;
};
```

Hard-limit continuation reuses the existing approval and pause/resume events.

## Testing

- Model runs can exceed the old eight-turn ceiling.
- `flash`, `thinking`, and `pro` resolve to the same default limits.
- Tool execution count increments only when the Capability Router starts a real
  execution.
- A hard model request limit pauses with approval instead of producing a raw
  run failure.
- Repeated identical tool calls warn at three repeats and pause at five.
