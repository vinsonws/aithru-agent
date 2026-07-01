# Agent Harness Gap Analysis & Implementation Roadmap

Status: accepted
Date: 2026-07-01

## Purpose

This document enumerates gaps between the current harness implementation and a
production-ready agent platform, ordered as a dependency-aware implementation
sequence.

The analysis covers 12 gaps across four phases, from correctness fixes to
performance polish.

---

## Current State Summary

**Solid & complete:**

- Run loop, model turn loop, context packet builder, terminal processors (title
  + summary), retry policy, run limits, scripted execution path
- Capability router interface + production router + policy engine (skill
  allow/deny, scopes, approvals)
- 10 local tools: workspace CRUD (5), todo CRUD (2), ask_clarification,
  presentation.present, skill.load
- Model adapters: OpenAI Responses API, Anthropic Messages API, SDK factory,
  test adapter, model profiles
- Persistence: InMemoryStore + SqliteStore, claims/leases, approvals, todos,
  documents, secrets, settings, context summaries
- Stream: 33 event types, event writer (visibility/redaction/source), SSE
  formatting, poll-based SSE stream
- Worker: WorkerRunner, claim acquire/release, stale claim recovery scanner
- API: Fastify routes for runs (CRUD + SSE), threads, approvals, health,
  compat, trace, snapshot, capability-audit
- Skills: loader, registry, resolver, activation events
- Subagents (scripted only), LocalMemoryProvider (KV + TTL), ControlledWeb
  provider, MCP catalog, WorkflowCapability HTTP adapter

**Gaps:** see sections below.

---

## Phase 1 — Correctness Foundation

These four items form the base layer. All subsequent work assumes they're done.

### Item 1: Provider-Native Tool Call Transcript Replay

**Problem:**

Current `context-packet.ts` builds a text summary of tool results and injects it
as a system message. This violates provider requirements:

- **Anthropic Messages API** requires `tool_use` + `tool_result` content blocks
  interleaved with `user`/`assistant` messages. Missing these causes HTTP 400.
- **OpenAI Responses API** requires `function_call` + `function_call_output`
  items in the `input` array.

The design doc explicitly states:

> This summary does not replace provider-native tool-call transcript replay.

**What to do:**

1. In `buildModelContextPacket`, when building messages for the model, serialize
   prior tool calls and their results into provider-native message formats.
2. Each model adapter (`provider-adapters.ts`) should define how to convert
   `AgentModelToolResult` back into its native message shape:
   - Anthropic: `{ role: "assistant", content: [tool_use block] }` followed by
     `{ role: "user", content: [tool_result block] }`
   - OpenAI: `{ role: "assistant", content: null, tool_calls: [...] }` followed
     by `{ role: "tool", tool_call_id, content }` in the `input` array
3. The existing text summary in system context can remain as supplemental
   information, but provider-native replay must be present for correctness.
4. Add integration tests that verify Anthropic and OpenAI model adapters accept
   multi-turn tool-call sequences without protocol errors.

**Files:** `context-packet.ts`, `model-turn.ts`, `provider-adapters.ts`,
`types.ts`

**Acceptance:**

- Multi-turn tool calls work on Anthropic without HTTP 400
- Multi-turn tool calls work on OpenAI Responses API without protocol errors
- Existing tests pass

---

### Item 2: Model Turn-Level Automatic Retry

**Problem:**

`retry.ts` defines exponential backoff but it is only used in
`RecoveryScanner` (worker-death recovery). When a model request fails with a
transient error (rate limit, 5xx, timeout), the `ModelTurnLoop` immediately
emits `RUN_FAILED`.

**What to do:**

1. Extend `AgentModelAdapter.createTurn()` or wrap it with a retry decorator
   that catches transient failures and retries with backoff.
2. Define which error codes are retryable: rate limit (429), server error (5xx)
   from the provider, network timeouts, and specific SDK error codes from
   Anthropic (`overloaded_error`, `rate_limit_error`) and OpenAI
   (`rate_limit_exceeded`, `server_error`).
3. Respect `AgentRunRetryPolicy` from the run's configuration. If retries
   exhausted, emit a non-retryable `RUN_FAILED`.
4. Each retry attempt should emit an audit event so the user can see the agent
   is retrying (not stuck).

**Files:** `model-turn.ts`, `retry.ts`, `provider-adapters.ts`

**Acceptance:**

- Rate-limited model requests retry automatically with backoff
- After exhausting retries, run fails with clear error
- Audit events emitted for each retry attempt

---

### Item 3: Run Cancellation with Actual Execution Interrupt

**Problem:**

`POST /api/runs/:run_id/cancel` only updates the database `status` to
`cancelled`. It does not stop an in-progress model request or tool execution.

**What to do:**

1. Thread an `AbortController` or `cancellationToken` from the API route through
   `scheduleRunExecution` → `ModelTurnLoop.execute()` → model adapter
   `createTurn()`.
2. The model adapters must accept an `AbortSignal` and pass it to the underlying
   HTTP request (OpenAI SDK / Anthropic SDK both support `signal`).
3. When a run is cancelled, the harness must:
   - Abort the current model request
   - Flush any pending tool call (do not start new ones)
   - Emit `RUN_CANCELLED`
   - Mark the run terminal
4. The SSE stream should detect `RUN_CANCELLED` and close cleanly (already
   handled by `TERMINAL_EVENT_TYPES`).

**Files:** `runtime.ts`, `model-turn.ts`, `sdk-adapters.ts`,
`provider-adapters.ts`, `routes/runs.ts`

**Acceptance:**

- Cancelling a run while a model request is in flight aborts the HTTP call
- No additional tool calls execute after cancellation
- SSE stream closes cleanly

---

### Item 4: User Input Submission Endpoint

**Problem:**

`ask_clarification` tool pauses the run with status `waiting_input` and emits
`INPUT_REQUESTED`. But there's no API endpoint for the user to submit their
response and resume the run.

**What to do:**

1. Add `POST /api/runs/:run_id/input` endpoint that accepts:

```json
{
  "input_request_id": "clarify_run_xxx_tc_yyy",
  "response": "user's answer"
}
```

2. On receiving input:
   - Emit `INPUT_RECEIVED`
   - Transition run status from `waiting_input` → `queued`
   - Build an `AgentModelToolResult` from the user's response
   - Call `scheduleRunExecution(run, { toolResults: [userInputResult] })`
3. The `ModelTurnLoop` already handles `toolResults` on entry and will continue
   the turn loop with the clarification result.

**Files:** `routes/runs.ts`, `approval-resolution.ts` (as reference pattern)

**Acceptance:**

- After `ask_clarification` pauses a run, submitting input resumes it
- The model receives the user's response and continues
- Invalid or duplicate `input_request_id` returns 400

---

## Phase 2 — Core Agent Tooling

With the correctness foundation in place, these items make the agent capable of
doing real work.

### Item 5: Code Execution / Sandbox Tool

**Problem:**

The agent can read/write files but cannot execute code, run shell commands, or
perform computation. This is the single biggest functional gap.

**What to do:**

1. Create a new `backend/packages/sandbox/` package with:
   - `SandboxExecutor`: spawns a child process in a workspace-scoped working
     directory, with:
     - Configurable timeout (default 30s, max 120s)
     - Max output size (default 64KB, truncate beyond)
     - Environment variable isolation (no host env vars except PATH and
       explicitly allowlisted ones)
     - stdin piping for the code/command
     - stdout + stderr capture
     - Exit code capture
   - `SandboxPolicy`: risk_level = `"high"`, requires_approval = `true` for
     write/network operations
2. Register two tool descriptors in `ProductionCapabilityRouter`:

```typescript
{
  name: "sandbox.execute",
  description: "Execute code or shell command in an isolated sandbox.",
  risk_level: "high",
  requires_approval: true,
  required_scopes: ["sandbox:execute"],
  input_schema: {
    type: "object",
    properties: {
      language: { type: "string", enum: ["bash", "python", "node", "auto"] },
      code: { type: "string" },
      timeout_ms: { type: "number", maximum: 120000 }
    },
    required: ["code"]
  }
}
```

3. Output shape:

```json
{
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "truncated": false
}
```

4. Redact secrets/tokens from stdout/stderr before returning to model (reuse
   redaction from `context-packet.ts`).
5. On first sandbox execution in a run, apply approval. Subsequent calls within
   the same run can auto-approve (if policy allows).

**Files:** new `packages/sandbox/`, `production-router.ts`, `policy.ts`

**Acceptance:**

- Agent can execute Python/Node/Bash code in workspace directory
- Timeout kills runaway processes
- Output is truncated if exceeds limit
- Approval required on first execution per run

---

### Item 6: Web Search / Fetch Tools

**Problem:**

`ControlledWebProvider` is fully implemented in `controlled-web.ts` but not
exposed as a tool.

**What to do:**

1. Register two tool descriptors in `ProductionCapabilityRouter`:

```typescript
{
  name: "web.fetch",
  description: "Fetch content from a URL (allowed hosts only).",
  risk_level: "medium",
  requires_approval: true,
  required_scopes: ["web:fetch"],
  input_schema: {
    type: "object",
    properties: {
      url: { type: "string", format: "uri" },
      max_chars: { type: "number", default: 10000 }
    },
    required: ["url"]
  }
},
{
  name: "web.search",
  description: "Search the web (requires configured search endpoint).",
  risk_level: "medium",
  requires_approval: true,
  required_scopes: ["web:search"],
  input_schema: {
    type: "object",
    properties: {
      query: { type: "string" }
    },
    required: ["query"]
  }
}
```

2. Inject `ControlledWebProvider` into `ProductionCapabilityRouter` constructor
   with `allowedHosts` from run config or skill policy.
3. Tool execution delegates to `provider.fetchUrl()` / `provider.search()`.
4. Host validation errors return clear messages (not raw exceptions).
5. Output is truncated to `max_chars` if specified.

**Files:** `production-router.ts`, `runtime.ts`, `controlled-web.ts`

**Acceptance:**

- `web.fetch` fetches allowed URLs, returns truncated text content
- `web.search` works when a search endpoint is configured
- Denied hosts return clear error, not 500
- Approval required by default; auto-approve can be configured

---

### Item 7: Memory Tools

**Problem:**

`LocalMemoryProvider` is fully implemented but not exposed as a tool.

**What to do:**

1. Register four tool descriptors in `ProductionCapabilityRouter`:

```typescript
{ name: "memory.remember", risk_level: "low", requires_approval: false,
  required_scopes: ["memory:write"],
  input_schema: { properties: { key: "string", value: "string", ttl_seconds: "number" }, required: ["key", "value"] } },
{ name: "memory.recall", risk_level: "low", requires_approval: false,
  required_scopes: ["memory:read"],
  input_schema: { properties: { key: "string" }, required: ["key"] } },
{ name: "memory.search", risk_level: "low", requires_approval: false,
  required_scopes: ["memory:read"],
  input_schema: { properties: { query: "string" }, required: ["query"] } },
{ name: "memory.forget", risk_level: "low", requires_approval: false,
  required_scopes: ["memory:write"],
  input_schema: { properties: { key: "string" }, required: ["key"] } }
```

2. Inject `LocalMemoryProvider` into `ProductionCapabilityRouter`.
3. Memory scope should be thread-wide (key namespace per thread_id).

**Files:** `production-router.ts`, `runtime.ts`

**Acceptance:**

- Agent can remember, recall, search, and forget information across turns
- Memory is scoped to the thread
- Keys with TTL expire automatically

---

## Phase 3 — Advanced Capabilities

### Item 8: Subagent Tool (Model-Driven Delegation)

**Problem:**

`SubagentRunner` only supports scripted execution. The model has no way to
delegate work to a subagent.

**What to do:**

1. Register tool descriptor:

```typescript
{
  name: "subagent.delegate",
  description: "Delegate a subtask to a child agent run.",
  risk_level: "high",
  requires_approval: true,
  required_scopes: ["subagent:delegate"],
  input_schema: {
    type: "object",
    properties: {
      task: { type: "string", description: "Task description for the child agent." },
      scopes: { type: "array", items: { type: "string" } }
    },
    required: ["task"]
  }
}
```

2. Subagent execution should use `ModelTurnLoop` (not `ScriptedHarness`):
   - Create child `AgentRun` with inherited `thread_id` and `workspace_id`
   - Run child through `ModelTurnLoop.execute()`
   - On completion, return result as tool output
   - Child runs should have stricter limits (e.g., 15 model requests, 30 tool
     executions)
3. Approvals: subagent delegation always requires approval. The approval
   payload should show the task description.

**Files:** `subagents/runner.ts`, `production-router.ts`, `model-turn.ts`

**Dependencies:** Requires Item 1 (tool replay in child runs too).

**Acceptance:**

- Agent can delegate a subtask and receive results
- Child runs are tracked independently with their own events
- Approval required for each delegation

---

### Item 9: Model-Driven Context Summarization

**Problem:**

Current `deriveContextSummary` in `terminal-processors.ts` is naive text
concatenation + truncation. The design doc already demonstrates model-driven
processing for title generation — the same pattern should apply to
summarization.

**What to do:**

1. Replace `deriveContextSummary` with a model-driven approach, similar to
   `generateThreadTitle`:
   - Collect messages that are about to fall out of context window
   - Build a summarization prompt
   - Call a lightweight model (same as `titleModelAdapter`) to produce a
     structured summary
2. The summary should be stored in `context_summaries` (already supported) and
   included in future context packets.
3. Progressive summarization: each new summary builds on the previous one rather
   than re-summarizing all dropped messages.
4. Fall back to the current naive approach if the model call fails.

**Files:** `terminal-processors.ts`

**Acceptance:**

- Long conversations get incremental, model-produced summaries
- Summaries are stored and replayed in context packets
- Falls back to text truncation on model failure

---

### Item 10: MCP Tool Integration

**Problem:**

`McpCatalog` and `McpProviderAdapter` exist but are not integrated into the
capability router. MCP server tools never appear in the agent's available tool
list.

**What to do:**

1. In `ProductionCapabilityRouter.listTools()`, append MCP tools from
   `McpProviderAdapter.listAvailableTools()`.
2. In `executeToolCall()`, route MCP-prefixed tools to an MCP execution path
   that calls the appropriate server (HTTP or stdio transport).
3. Apply the same policy/approval/scope checks as local tools.
4. MCP tool results follow the same `AgentToolCallResult` contract.

**Files:** `production-router.ts`, `external/mcp.ts`

**Acceptance:**

- MCP server tools appear in agent's tool list alongside built-in tools
- MCP tools go through capability router, policy, and approval flow
- Tool execution works for both HTTP and stdio MCP transports

---

## Phase 4 — Polish & Observability

### Item 11: Push-Based SSE Streaming

**Problem:**

Current SSE implementation polls the event store every 100ms. This adds latency
and wastes CPU.

**What to do:**

1. Add an `EventEmitter` (or `Subject`-like) to `AgentEventWriter` that emits
   on every `write()` call.
2. Replace the poll loop in `writeRunStream` with an event listener pattern.
   Keep the keepalive (15s) for connection health.
3. Ensure backpressure handling: if the client is slow, buffer events up to a
   limit, then drop with a warning.
4. The `after_sequence` query parameter still works: replay events up to the
   current cursor, then start pushing.

**Files:** `stream/writer.ts`, `stream/store.ts`, `routes/run-stream.ts`

**Acceptance:**

- SSE events arrive within ~10ms of emission (not 100ms)
- Keepalive still sent every 15s
- Backpressure doesn't crash the server

---

### Item 12: Workspace File-to-Run Association

**Problem:**

Workspace files only have `workspace_id` with no traceability to which run
created or modified them. This makes audit and debugging harder.

**What to do:**

1. Add optional fields to `WorkspaceFile`:

```typescript
created_by_run_id?: string;
last_modified_by_run_id?: string;
```

2. Update `FileWorkspaceStore.writeFile()` to accept and store `run_id`.
3. Pass `run.id` from tool execution context (`executeToolCall`) when writing
   files.
4. `listWorkspaceFiles` can optionally filter by `created_by_run_id`.
5. Add a `GET /api/runs/:run_id/files` endpoint that returns files created or
   modified by that run.

**Files:** `persistence/store.ts`, `persistence/workspace-files.ts`,
`production-router.ts`, `routes/runs.ts`

**Acceptance:**

- Every workspace file records which run created it and last modified it
- Querying files by run is possible through API and store

---

## Dependency Graph

```
Phase 1:              Phase 2:           Phase 3:            Phase 4:
[1] tool replay ─────→ [5] sandbox
    │                   
    ├──→ [2] retry ───→ [6] web           [8] subagent ────→ [11] push SSE
    │                                    ↗
    ├──→ [3] cancel                      [9] summary        [12] file-run link
    │                                 ↗
    └──→ [4] input endpoint            [10] MCP

(→ means "unblocks"; items within a phase can run in parallel)
```

---

## Implementation Notes

### For Each Item

1. Read the relevant existing code first (paths specified in each item).
2. Write or update tests before implementation changes.
3. Run verification after each item:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

4. Avoid introducing new dependencies without explicit justification.
5. Tool descriptors follow the pattern in `production-router.ts` —
   `risk_level`, `requires_approval`, `required_scopes`, `input_schema`.
6. All tool execution goes through `ProductionCapabilityRouter.executeToolCall()`,
   never bypassing the capability boundary.

### Boundaries

- Do not expose unrestricted host filesystem, network, or process access to
  model tools.
- Sandbox execution must be constrained to the workspace directory.
- Web fetch must only hit allowed hosts.
- Subagent runs must have their own limit budgets.
- All new tools require scope definitions and go through
  `PolicyEngine.checkToolCall()`.

---

## Milestone Summary

| Milestone | Items | Outcome |
|---|---|---|
| **M1: Correct & Reliable** | #1, #2 | Multi-turn tool calls work on all providers, transient errors auto-retry |
| **M2: Controlled Lifecycle** | #3, #4 | Runs are cancellable, pausable for user input, full control plane |
| **M3: Capable Agent** | #5, #6, #7 | Code execution + web access + memory = agent can do real work |
| **M4: Advanced** | #8, #9, #10 | Subagents, long-context quality, MCP ecosystem |
| **M5: Production Polish** | #11, #12 | Low-latency streaming, file audit trail |
