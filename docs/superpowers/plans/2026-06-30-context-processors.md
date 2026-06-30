# Context Processors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tool result context, thread title generation, and durable context summaries without reintroducing `agent_documents` or memory behavior.

**Architecture:** Keep display messages as complete thread history and build a separate bounded model context packet before each model turn. Add terminal processors that run after completed model runs for title and context summary updates. Treat live thinking/tool-call chains as provider-native transcript data, not as summarizable tool result context.

**Tech Stack:** TypeScript, Vitest, sql.js, Fastify runtime scheduler, OpenAI/Anthropic SDK adapters.

## Global Constraints

- No Python backend.
- Real tool actions must continue through the Capability Router.
- Provider SDK objects stay inside `backend/packages/model/src`; do not make SDK response objects public Aithru contracts.
- `workspace_files`, `workspace_file_versions`, and `agent_documents` database tables stay removed.
- Memory is out of scope for this plan.
- Tool result context is model-only context; it must not create user-visible display messages.
- Provider-native thinking/tool-call chains must preserve the exact message shape required by that provider, or fail clearly before sending a malformed request.

---

## Provider Transcript Finding

Reasoning-capable providers do not all use the same transcript shape. DeepSeek-style OpenAI-compatible APIs may expose `reasoning_content`, Anthropic uses thinking/tool blocks, and other OpenAI-compatible vendors such as Qwen, GLM, and Kimi can differ in request knobs and returned fields.

Design consequence: `tool result context` may summarize old completed tool outputs for future turns, but it must never replace the live provider-native tool-call transcript during an interleaved thinking/tool loop. Provider-specific transcript details belong only in `backend/packages/model/src`.

## File Structure

- Create `backend/packages/harness/src/context-packet.ts`
  - Builds model-only context packets from stored messages, current run events, and latest context summary.
  - Produces synthetic `system` context messages that are not persisted.
- Create `backend/packages/harness/src/terminal-processors.ts`
  - Runs `maybeGenerateThreadTitle` and `maybeCreateContextSummary` after terminal model runs.
- Modify `backend/packages/harness/src/model-turn.ts`
  - Replace local `buildModelContextMessages` with `buildModelContextPacket`.
  - Emit richer `context.packet.built` stats.
- Modify `backend/packages/harness/src/index.ts`
  - Export the new context packet and terminal processor helpers.
- Modify `backend/packages/model/src/sdk-adapters.ts`
  - Add a guard for SDK native tool-call requests with pending `toolResults` until native transcript replay exists.
- Modify `backend/packages/model/src/types.ts`
  - No new public provider SDK types in this pass. Keep `toolResults` as provider-neutral Aithru results.
- Modify `backend/packages/persistence/src/store.ts`
  - Add `AgentContextSummary` and in-memory summary methods.
- Modify `backend/packages/persistence/src/protocols.ts`
  - Add `createContextSummary`, `listContextSummaries`, and `getLatestContextSummary`.
- Modify `backend/packages/persistence/src/migrations.ts`
  - Add dedicated `context_summaries` table and index.
- Modify `backend/packages/persistence/src/sqlite-store.ts`
  - Persist context summaries in the dedicated table.
- Modify `backend/packages/stream/src/events.ts`
  - Add `context.summary.created` and `thread.title.generated`.
- Modify `backend/apps/api/src/runtime.ts`
  - Run terminal processors after `ModelTurnLoop.execute`.
- Test `backend/tests/model/model-turn.test.ts`
  - Context packet, tool result context, and summary injection.
- Test `backend/tests/model/sdk-adapters.test.ts`
  - Provider-native tool transcript guard.
- Test `backend/tests/persistence/sqlite-store.test.ts`
  - Context summary table persistence.
- Test `backend/tests/integration/api.test.ts`
  - Title generation through API-driven run completion.
- Update `docs/00-agent-harness-design.md`
  - Document display history vs model context, tool result context, terminal processors, and memory deferral.

---

### Task 1: Guard SDK Native Tool Chains Before Context Work

**Files:**
- Modify: `backend/packages/model/src/sdk-adapters.ts`
- Test: `backend/tests/model/sdk-adapters.test.ts`

**Interfaces:**
- Consumes: `AgentModelTurnInput.toolResults`
- Produces: a clear `NATIVE_TOOL_TRANSCRIPT_REQUIRED` failure when a provider request declares native tools and the loop is trying to continue with summarized `toolResults`.

- [ ] **Step 1: Write the failing test**

Add this test to `backend/tests/model/sdk-adapters.test.ts`:

```ts
it("fails clearly instead of faking native tool transcript replay", () => {
  expect(() =>
    buildOpenAIChatCompletionRequest(
      {
        apiKey: "test",
        provider: "custom",
        model: "thinking-tool-model",
        metadata: {
          compat: "qwen",
          request: {
            tools: [
              {
                type: "function",
                function: {
                  name: "todo.create",
                  description: "Create a todo",
                  parameters: { type: "object", properties: {} },
                },
              },
            ],
          },
          when_thinking_enabled: { extra_body: { thinking: { type: "enabled" } } },
        },
      },
      { ...input("high"), toolResults: [{ id: "call_1", name: "todo.create", output: { ok: true } }] },
    ),
  ).toThrow(/NATIVE_TOOL_TRANSCRIPT_REQUIRED/);
});
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
cd backend
npm run test -- tests/model/sdk-adapters.test.ts
```

Expected: the new test fails because the builder currently ignores `toolResults`.

- [ ] **Step 3: Add the guard**

In `backend/packages/model/src/sdk-adapters.ts`, add helpers near `baseRequest`:

```ts
function requestDeclaresTools(request: Record<string, unknown>): boolean {
  return Array.isArray(request.tools) && request.tools.length > 0;
}

function assertNoFakeNativeToolReplay(
  request: Record<string, unknown>,
  input: AgentModelTurnInput,
): void {
  if (input.toolResults.length > 0 && requestDeclaresTools(request)) {
    throw new Error(
      "NATIVE_TOOL_TRANSCRIPT_REQUIRED: provider-native tool calls need exact assistant/tool transcript replay",
    );
  }
}
```

Call it in `buildOpenAIChatCompletionRequest`, `buildOpenAIResponsesRequest`, and `buildAnthropicMessagesRequest` after `baseRequest(...)` is built and before returning.

- [ ] **Step 4: Run the focused test again**

Run:

```bash
cd backend
npm run test -- tests/model/sdk-adapters.test.ts
```

Expected: pass.

---

### Task 2: Build Model Context Packets With Recent Tool Results

**Files:**
- Create: `backend/packages/harness/src/context-packet.ts`
- Modify: `backend/packages/harness/src/model-turn.ts`
- Modify: `backend/packages/harness/src/index.ts`
- Test: `backend/tests/model/model-turn.test.ts`

**Interfaces:**
- Consumes:
  - `AgentMessage[]`
  - `AgentStreamEvent[]`
  - optional latest `AgentContextSummary`
- Produces:
  - `buildModelContextPacket(args): ModelContextPacket`
  - `packet.messages`: bounded persisted messages plus optional synthetic model-only `system` context message
  - `packet.stats`: audit payload for `context.packet.built`

- [ ] **Step 1: Write the failing test**

Add a test to `backend/tests/model/model-turn.test.ts` that creates a run, appends a `tool.completed` event, executes a model turn, and asserts the adapter sees a synthetic system message containing `Recent tool results`.

```ts
it("injects recent tool results as model-only context", async () => {
  const store = new InMemoryStore();
  const eventWriter = new AgentEventWriter(store);
  const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
  const run = createRun();
  const threadId = "thread_tool_context";
  store.createThread({
    id: threadId,
    org_id: "org_1",
    owner_user_id: "user_1",
    title: "Tool context",
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  });
  store.createRun({ ...run, thread_id: threadId });
  eventWriter.write(run.id, threadId, "tool.completed", {
    tool_call_id: "tc_1",
    name: "todo.create",
    output: { id: "todo_1", title: "Ship it", status: "pending" },
  });

  const loop = new ModelTurnLoop({
    store,
    eventWriter,
    capabilityRouter,
    modelAdapter: new TestModelAdapter([
      (input) => {
        expect(input.messages[0].role).toBe("system");
        expect(input.messages[0].content).toContain("Recent tool results");
        expect(input.messages[0].content).toContain("todo.create");
        return [{ type: "text_delta", delta: "ok" }, { type: "completed" }];
      },
    ]),
  });

  await loop.execute({ ...run, thread_id: threadId });
  expect(store.listMessages(threadId).some((message) => message.role === "system")).toBe(false);
});
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
cd backend
npm run test -- tests/model/model-turn.test.ts
```

Expected: fail because context packet code does not exist.

- [ ] **Step 3: Create the packet builder**

Create `backend/packages/harness/src/context-packet.ts` with these exported shapes:

```ts
import type { AgentMessage, AgentRun, AgentStreamEvent } from "@aithru-agent/contracts";
import type { AgentContextSummary } from "@aithru-agent/persistence";

export const MODEL_CONTEXT_MESSAGE_LIMIT = 12;
export const MODEL_CONTEXT_CONTENT_LIMIT = 1000;
export const MODEL_CONTEXT_TOOL_RESULT_LIMIT = 8;

export interface ModelContextPacket {
  messages: AgentMessage[];
  stats: {
    total_messages: number;
    included_messages: number;
    dropped_messages: number;
    truncated_messages: number;
    included_tool_results: number;
    truncated_tool_results: number;
    included_summary: boolean;
  };
}
```

Implement these helpers in the same file:

```ts
function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function redactSensitiveKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactSensitiveKeys);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, child]) => [
      key,
      /token|secret|password|api[_-]?key/i.test(key) ? "[redacted]" : redactSensitiveKeys(child),
    ]),
  );
}

function compactJson(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(redactSensitiveKeys(value));
  return text.length > MODEL_CONTEXT_CONTENT_LIMIT
    ? `${text.slice(0, MODEL_CONTEXT_CONTENT_LIMIT)}...`
    : text;
}
```

`buildModelContextPacket` should:

1. Keep the last 12 stored messages.
2. Truncate each message content to 1000 characters for model input only.
3. Read latest 8 `tool.completed` or `tool.failed` events from the current run events.
4. Format a synthetic system message only when there is a latest summary or tool result context:

```txt
Context summary:
...

Recent tool results:
- tool.name (tool_call_id): compact output or error
```

5. Put the synthetic system message before bounded stored messages.

- [ ] **Step 4: Wire `ModelTurnLoop`**

In `backend/packages/harness/src/model-turn.ts`, remove local `buildModelContextMessages`. Inside the turn loop:

```ts
const fullMessages = currentRun.thread_id
  ? this.deps.store.listMessages(currentRun.thread_id)
  : [];
const contextPacket = buildModelContextPacket({
  run: currentRun,
  messages: fullMessages,
  events: this.deps.store.listEvents(run.id),
  latestSummary: currentRun.thread_id
    ? this.deps.store.getLatestContextSummary(currentRun.thread_id)
    : undefined,
});
```

Pass `contextPacket.messages` to the adapter and `contextPacket.stats` as `context`.

- [ ] **Step 5: Export the builder**

Add to `backend/packages/harness/src/index.ts`:

```ts
export * from "./context-packet.js";
```

- [ ] **Step 6: Run the focused test again**

Run:

```bash
cd backend
npm run test -- tests/model/model-turn.test.ts
```

Expected: pass.

---

### Task 3: Persist Context Summaries

**Files:**
- Modify: `backend/packages/persistence/src/store.ts`
- Modify: `backend/packages/persistence/src/protocols.ts`
- Modify: `backend/packages/persistence/src/migrations.ts`
- Modify: `backend/packages/persistence/src/sqlite-store.ts`
- Test: `backend/tests/persistence/sqlite-store.test.ts`

**Interfaces:**
- Produces:

```ts
export interface AgentContextSummary {
  id: string;
  org_id: string;
  thread_id: string;
  run_id: string;
  summary: string;
  source_message_count: number;
  created_at: string;
}
```

Store methods:

```ts
createContextSummary(summary: AgentContextSummary): AgentContextSummary;
listContextSummaries(threadId: string): AgentContextSummary[];
getLatestContextSummary(threadId: string): AgentContextSummary | undefined;
```

- [ ] **Step 1: Write the failing SQLite test**

Add to `backend/tests/persistence/sqlite-store.test.ts`:

```ts
it("persists context summaries outside agent_documents", async () => {
  const dbPath = join(tempDir, "context-summary.sqlite");
  const durable = await SqliteStore.create(dbPath);
  durable.createContextSummary({
    id: "summary_1",
    org_id: "org_1",
    thread_id: "thread_1",
    run_id: "run_1",
    summary: "Older conversation summary.",
    source_message_count: 14,
    created_at: "2026-01-01T00:00:00Z",
  });
  durable.close();

  const reopened = await SqliteStore.create(dbPath);
  try {
    expect(reopened.getLatestContextSummary("thread_1")?.summary).toBe("Older conversation summary.");
  } finally {
    reopened.close();
  }
});
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
cd backend
npm run test -- tests/persistence/sqlite-store.test.ts
```

Expected: fail because store methods do not exist.

- [ ] **Step 3: Add in-memory summary storage**

In `backend/packages/persistence/src/store.ts`, add `AgentContextSummary`, a private `contextSummaries` map, and the three methods above. Sort summaries by `created_at ASC`, and let `getLatestContextSummary` return the last item.

- [ ] **Step 4: Add protocol methods**

In `backend/packages/persistence/src/protocols.ts`, import `AgentContextSummary` and add the three methods to `AgentStore`.

- [ ] **Step 5: Add SQLite DDL**

In `backend/packages/persistence/src/migrations.ts`, add:

```sql
CREATE TABLE IF NOT EXISTS context_summaries (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  source_message_count INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_context_summaries_thread
  ON context_summaries(thread_id, created_at);
```

- [ ] **Step 6: Add SQLite methods**

In `backend/packages/persistence/src/sqlite-store.ts`, implement inserts/selects with plain columns. Do not use `upsertDocument`.

- [ ] **Step 7: Run the focused test again**

Run:

```bash
cd backend
npm run test -- tests/persistence/sqlite-store.test.ts
```

Expected: pass.

---

### Task 4: Add Terminal Processors for Title and Summary

**Files:**
- Create: `backend/packages/harness/src/terminal-processors.ts`
- Modify: `backend/packages/harness/src/index.ts`
- Modify: `backend/packages/stream/src/events.ts`
- Modify: `backend/apps/api/src/runtime.ts`
- Test: `backend/tests/integration/api.test.ts`
- Test: `backend/tests/model/model-turn.test.ts`

**Interfaces:**
- Produces:

```ts
export async function runTerminalProcessors(deps: {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  run: AgentRun;
}): Promise<void>;
```

- [ ] **Step 1: Write title generation test**

Add an integration test that creates a thread with `title: null`, runs a model-backed request, waits for completion, and asserts the thread title is no longer null. Also add a second assertion that a manually titled thread is not overwritten.

- [ ] **Step 2: Write summary creation test**

In `backend/tests/model/model-turn.test.ts`, create a thread with 13 messages, execute a completed run, call `runTerminalProcessors`, and assert `store.getLatestContextSummary(threadId)` exists.

- [ ] **Step 3: Run focused tests**

Run:

```bash
cd backend
npm run test -- tests/model/model-turn.test.ts tests/integration/api.test.ts
```

Expected: fail because processors do not exist.

- [ ] **Step 4: Add stream event names**

In `backend/packages/stream/src/events.ts`, add:

```ts
CONTEXT_SUMMARY_CREATED: "context.summary.created",
THREAD_TITLE_GENERATED: "thread.title.generated",
```

- [ ] **Step 5: Implement title helper**

In `backend/packages/harness/src/terminal-processors.ts`, implement:

```ts
function stripThinkingText(content: string): string {
  return content
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/```(?:thinking|reasoning)[\s\S]*?```/gi, "")
    .trim();
}

function deriveThreadTitle(messages: AgentMessage[]): string | null {
  const user = messages.find((message) => message.role === "user")?.content ?? "";
  const cleaned = stripThinkingText(user)
    .replace(/[#*_`>\[\]()]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return null;
  return cleaned.length > 60 ? `${cleaned.slice(0, 57).trim()}...` : cleaned;
}
```

`maybeGenerateThreadTitle` should:

1. Require `run.status === "completed"` and `run.thread_id`.
2. Skip when `thread.title` is non-empty.
3. Derive the title from the first user message.
4. Update `thread.title` and `thread.updated_at`.
5. Emit `thread.title.generated`.

- [ ] **Step 6: Implement deterministic summary helper**

In the same file:

```ts
const SUMMARY_MESSAGE_THRESHOLD = MODEL_CONTEXT_MESSAGE_LIMIT + 1;
const SUMMARY_LIMIT = 1000;

function deriveContextSummary(messages: AgentMessage[]): string {
  const olderMessages = messages.slice(0, -MODEL_CONTEXT_MESSAGE_LIMIT);
  const text = olderMessages
    .map((message) => `${message.role}: ${stripThinkingText(message.content)}`)
    .join("\n")
    .replace(/\s+/g, " ")
    .trim();
  return text.length > SUMMARY_LIMIT ? `${text.slice(0, SUMMARY_LIMIT).trim()}...` : text;
}
```

`maybeCreateContextSummary` should:

1. Require `run.status === "completed"` and `run.thread_id`.
2. Require `messages.length >= SUMMARY_MESSAGE_THRESHOLD`.
3. Skip when the latest summary already has `source_message_count >= messages.length`.
4. Store `summary_${run.id}` with current message count.
5. Emit `context.summary.created`.

- [ ] **Step 7: Wire processors after model execution**

In `backend/apps/api/src/runtime.ts`, after `const completed = await loop.execute(run);`, call:

```ts
const completed = await loop.execute(run);
if (completed?.status === "completed") {
  await runTerminalProcessors({
    store: deps.store,
    eventWriter: deps.eventWriter,
    run: completed,
  });
}
return deps.store.getRun(run.id);
```

- [ ] **Step 8: Export processors**

Add to `backend/packages/harness/src/index.ts`:

```ts
export * from "./terminal-processors.js";
```

- [ ] **Step 9: Run focused tests again**

Run:

```bash
cd backend
npm run test -- tests/model/model-turn.test.ts tests/integration/api.test.ts
```

Expected: pass.

---

### Task 5: Documentation and Full Verification

**Files:**
- Modify: `docs/00-agent-harness-design.md`

**Interfaces:**
- Produces a documented boundary:
  - Display messages are complete thread-visible history.
  - Model context packets are bounded and may include summaries/tool result context.
  - Memory is deliberately excluded.
  - Interleaved thinking/tool-call providers require exact native transcript replay before SDK-native tools can be enabled.

- [ ] **Step 1: Update design docs**

Add a short section to `docs/00-agent-harness-design.md`:

```md
### Display History vs Model Context

Agent Thread messages remain the complete user-visible conversation record.
Before each model turn, the harness builds a bounded model context packet from
thread messages, recent tool result summaries, and the latest context summary.
The packet is model input only and is not displayed as chat history.

### Tool Result Context

Completed tool outputs may be summarized into model-only context so later turns
can reason over what happened without replaying large raw outputs. This summary
does not replace provider-native tool-call transcript replay. Reasoning-capable
providers may require exact assistant reasoning/tool-call fields and matching
tool result messages during live tool-call chains.

### Terminal Processors

After completed model runs, terminal processors may derive a thread title and a
context summary. Memory extraction is intentionally out of scope for this
processor set.
```

- [ ] **Step 2: Run complete backend verification**

Run:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

Expected: all pass.

---

## Deferred Work

- Provider-native transcript replay for SDK tool calls:
  - OpenAI-compatible: preserve the provider's assistant reasoning field, `content`, `tool_calls`, then append matching `role: "tool"` messages.
  - Anthropic: preserve thinking/tool_use/tool_result content blocks in Anthropic format inside the adapter.
  - Only after this exists should real SDK provider tool-calling be enabled.
- Model-generated title and context summary:
  - The first implementation should use deterministic local processors.
  - Add optional model-based processors later if quality becomes a problem.
- Memory:
  - Deliberately excluded.

## Self-Review

- Spec coverage: includes tool result context, title processor, context summary, and explicitly excludes memory.
- Provider coverage: documents why summarized tool result context cannot replace native interleaved thinking transcript.
- Storage boundary: uses `context_summaries`, not `agent_documents`.
- Capability boundary: tool execution remains in Capability Router; processors only read stored messages/events and write titles/summaries.
- Test coverage: includes model context, SDK guard, persistence, integration, and full backend verification.
