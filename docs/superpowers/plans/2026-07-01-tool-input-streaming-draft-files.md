# Tool Input Streaming Draft Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream tool-call input deltas to the frontend and show `workspace.write_file` content as a live draft file preview before approval and execution.

**Architecture:** Add one generic backend stream event, `tool.input_delta`, that observes provider tool argument chunks without executing tools. The frontend accumulates those chunks as tool input drafts, derives draft workspace files only for `workspace.write_file`, and reuses the existing file preview panel until the real workspace file replaces the draft.

**Tech Stack:** TypeScript, Fastify backend packages, Vitest backend tests, React frontend, TanStack Query, node:test frontend tests with esbuild.

## Global Constraints

- The Agent runtime remains an AI harness, not a workflow graph or scheduler.
- Real tool execution must continue through the Aithru Capability Router.
- `tool.input_delta` is observational only and must not execute tools, create approvals, or mutate run status.
- `tool.proposed` remains the first complete tool proposal that enters policy, approval, and execution.
- Do not add filesystem watchers.
- Do not add `append` or `workspace.append_file` in this implementation.
- Do not add provider-specific frontend event shapes.
- Do not add new dependencies.
- New frontend tests use the existing `node --test` plus esbuild pattern.
- Meaningful backend verification must run: `cd backend && npm run typecheck && npm run test && npm run check:no-python-backend && npm run examples:file-report`.

---

## File Structure

Backend files:

- Modify `backend/packages/stream/src/events.ts`: add `TOOL_INPUT_DELTA`.
- Modify `backend/packages/model/src/types.ts`: add `tool_input_delta` to `ModelTurnEvent` and add `inputStreamId` to complete tool calls.
- Modify `backend/packages/model/src/sdk-adapters.ts`: emit tool input deltas for OpenAI Chat Completions and OpenAI Responses.
- Modify `backend/packages/model/src/provider-adapters.ts`: keep the OpenAI-compatible test adapter aligned with Responses-style deltas.
- Modify `backend/packages/harness/src/model-turn.ts`: forward `tool_input_delta` to the event stream only.
- Modify `backend/packages/harness/src/run-loop.ts`: carry `inputStreamId` into `tool.proposed`.
- Modify `backend/tests/model/sdk-adapters.test.ts`: cover OpenAI SDK delta ordering and id binding.
- Modify `backend/tests/model/provider-adapters.test.ts`: cover the OpenAI-compatible adapter shape.
- Modify `backend/tests/model/model-turn.test.ts`: prove the harness does not execute tools for deltas.

Frontend files:

- Modify `frontend/src/features/chat/useRunStream.ts`: add `ToolInputDraft` state and reducer cases.
- Modify `frontend/src/features/inspection/runFilesView.ts`: add draft file projection helpers and draft-aware file views.
- Modify `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx`: render draft content without workspace fetches.
- Modify `frontend/src/features/sidebar/panels/FileListPanel.tsx`: include draft views in the file list.
- Modify `frontend/src/AppShell.tsx`: derive draft files from stream state, pass them to panels, and auto-open the first live draft once.
- Modify `frontend/tests/use-run-stream.test.mjs`: cover tool input draft replay.
- Modify `frontend/tests/run-files-view.test.mjs`: cover draft file projection and real-file replacement.
- Add `frontend/tests/file-preview-drafts.test.mjs`: source-level guard for draft rendering and `srcDoc`.
- Modify `frontend/tests/app-shell-actions.test.mjs`: source-level guard for draft wiring and one-shot auto-open.

---

### Task 1: Backend Tool Input Delta Event

**Files:**
- Modify: `backend/packages/stream/src/events.ts`
- Modify: `backend/packages/model/src/types.ts`
- Modify: `backend/packages/model/src/sdk-adapters.ts`
- Modify: `backend/packages/model/src/provider-adapters.ts`
- Modify: `backend/packages/harness/src/model-turn.ts`
- Modify: `backend/packages/harness/src/run-loop.ts`
- Test: `backend/tests/model/sdk-adapters.test.ts`
- Test: `backend/tests/model/provider-adapters.test.ts`
- Test: `backend/tests/model/model-turn.test.ts`

**Interfaces:**
- Consumes: provider chunk streams already handled by `OpenAISdkModelAdapter` and `OpenAICompatibleAdapter`.
- Produces: `ModelTurnEvent` branch `{ type: "tool_input_delta"; inputStreamId: string; toolCallId?: string; index?: number; name?: string; delta: string }`.
- Produces: stream event payload `{ input_stream_id: string; tool_call_id: string | null; index: number | null; name: string | null; input_delta: string }`.

- [ ] **Step 1: Write failing SDK adapter tests**

Add these tests to `backend/tests/model/sdk-adapters.test.ts` inside the existing SDK model adapter describe block:

```ts
  it("streams OpenAI chat tool argument deltas before the final tool call", async () => {
    async function* chunks() {
      yield {
        choices: [
          {
            delta: {
              tool_calls: [
                {
                  index: 0,
                  id: "call_1",
                  function: { name: "todo_create", arguments: '{"title"' },
                },
              ],
            },
          },
        ],
      };
      yield {
        choices: [
          {
            delta: {
              tool_calls: [
                {
                  index: 0,
                  function: { arguments: ':"Ship it"}' },
                },
              ],
            },
          },
        ],
      };
    }

    const adapter = new OpenAISdkModelAdapter({
      apiKey: "test",
      provider: "openai",
      model: "gpt-test",
    }) as any;

    const events = await collectModelEvents(
      adapter.createChatCompletionTurn(
        { chat: { completions: { create: () => chunks() } } },
        inputWithTools(),
      ),
    );

    expect(events).toEqual([
      {
        type: "tool_input_delta",
        inputStreamId: "chat:0",
        toolCallId: "call_1",
        index: 0,
        name: "todo.create",
        delta: '{"title"',
      },
      {
        type: "tool_input_delta",
        inputStreamId: "chat:0",
        toolCallId: "call_1",
        index: 0,
        name: "todo.create",
        delta: ':"Ship it"}',
      },
      {
        type: "tool_call",
        id: "call_1",
        inputStreamId: "chat:0",
        name: "todo.create",
        input: { title: "Ship it" },
      },
      { type: "completed", content: "" },
    ]);
  });

  it("streams OpenAI Responses argument deltas with the final input stream id", async () => {
    async function* events() {
      yield {
        type: "response.function_call_arguments.delta",
        item_id: "item_1",
        delta: '{"title"',
      };
      yield {
        type: "response.function_call_arguments.delta",
        item_id: "item_1",
        delta: ':"Ship it"}',
      };
      yield {
        type: "response.output_item.done",
        item: {
          id: "item_1",
          type: "function_call",
          call_id: "call_1",
          name: "todo_create",
          arguments: '{"title":"Ship it"}',
        },
      };
    }

    const adapter = new OpenAISdkModelAdapter({
      apiKey: "test",
      provider: "openai",
      model: "gpt-test",
      metadata: { use_responses_api: true },
    }) as any;

    const modelEvents = await collectModelEvents(
      adapter.createResponsesTurn(
        { responses: { create: () => events() } },
        inputWithTools(),
      ),
    );

    expect(modelEvents).toEqual([
      {
        type: "tool_input_delta",
        inputStreamId: "item_1",
        index: undefined,
        name: undefined,
        toolCallId: undefined,
        delta: '{"title"',
      },
      {
        type: "tool_input_delta",
        inputStreamId: "item_1",
        index: undefined,
        name: undefined,
        toolCallId: undefined,
        delta: ':"Ship it"}',
      },
      {
        type: "tool_call",
        id: "call_1",
        inputStreamId: "item_1",
        name: "todo.create",
        input: { title: "Ship it" },
      },
      { type: "completed", content: "" },
    ]);
  });
```

- [ ] **Step 2: Write failing compatible adapter test**

Add this test to `backend/tests/model/provider-adapters.test.ts`:

```ts
  it("normalizes OpenAI-compatible argument deltas", async () => {
    const adapter = new OpenAICompatibleAdapter(() => [
      {
        type: "response.function_call_arguments.delta",
        item_id: "item_1",
        delta: '{"title"',
      },
      {
        type: "response.function_call_arguments.delta",
        item_id: "item_1",
        delta: ':"x"}',
      },
      {
        type: "response.output_item.done",
        item: {
          id: "item_1",
          type: "function_call",
          call_id: "call_1",
          name: "todo.create",
          arguments: '{"title":"x"}',
        },
      },
    ]);

    const events = await collectModelEvents(adapter.createTurn(input));
    expect(events).toEqual([
      {
        type: "tool_input_delta",
        inputStreamId: "item_1",
        toolCallId: undefined,
        index: undefined,
        name: undefined,
        delta: '{"title"',
      },
      {
        type: "tool_input_delta",
        inputStreamId: "item_1",
        toolCallId: undefined,
        index: undefined,
        name: undefined,
        delta: ':"x"}',
      },
      {
        type: "tool_call",
        id: "call_1",
        inputStreamId: "item_1",
        name: "todo.create",
        input: { title: "x" },
      },
    ]);
  });
```

- [ ] **Step 3: Write failing harness test**

Add these tests to `backend/tests/model/model-turn.test.ts`:

```ts
  it("forwards streamed tool input without executing or approving a tool", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun(run);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          {
            type: "tool_input_delta",
            inputStreamId: "chat:0",
            toolCallId: "call_1",
            index: 0,
            name: "workspace.write_file",
            delta: '{"path":"/draft.md"',
          },
          { type: "completed" },
        ],
      ]),
    });

    const completed = await loop.execute(run);

    expect(completed.status).toBe("completed");
    expect(store.listApprovals(run.id)).toEqual([]);
    expect(store.listWorkspaceFiles(run.workspace_id)).toEqual([]);
    expect(store.listEvents(run.id).map((event) => event.type)).toContain("tool.input_delta");
    expect(store.listEvents(run.id).map((event) => event.type)).not.toContain("tool.proposed");
    expect(store.listEvents(run.id).map((event) => event.type)).not.toContain("tool.started");
  });

  it("carries input stream ids into final tool proposal events", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun(run);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          {
            type: "tool_input_delta",
            inputStreamId: "chat:0",
            toolCallId: "model_tc_1",
            index: 0,
            name: "todo.create",
            delta: '{"title":"From stream"}',
          },
          {
            type: "tool_call",
            id: "model_tc_1",
            inputStreamId: "chat:0",
            name: "todo.create",
            input: { title: "From stream" },
          },
          { type: "completed" },
        ],
      ]),
    });

    const completed = await loop.execute(run);
    const proposed = store
      .listEvents(run.id)
      .find((event) => event.type === "tool.proposed")!;

    expect(completed.status).toBe("completed");
    expect((proposed.payload as Record<string, unknown>).input_stream_id).toBe("chat:0");
  });
```

- [ ] **Step 4: Run backend tests to verify they fail**

Run:

```bash
cd backend
npm run test -- tests/model/sdk-adapters.test.ts tests/model/provider-adapters.test.ts tests/model/model-turn.test.ts
```

Expected: FAIL because `tool_input_delta`, `inputStreamId`, and `tool.input_delta` are not defined yet.

- [ ] **Step 5: Add backend event and model types**

In `backend/packages/stream/src/events.ts`, add this entry in the Tool lifecycle block:

```ts
  TOOL_INPUT_DELTA: "tool.input_delta",
```

In `backend/packages/model/src/types.ts`, replace the `tool_call` branch with these two branches:

```ts
  | {
      type: "tool_input_delta";
      inputStreamId: string;
      toolCallId?: string;
      index?: number;
      name?: string;
      delta: string;
    }
  | {
      type: "tool_call";
      id: string;
      inputStreamId?: string;
      name: string;
      input: Record<string, unknown>;
    }
```

- [ ] **Step 6: Emit OpenAI Chat Completions deltas**

In `backend/packages/model/src/sdk-adapters.ts`, change the chat tool call map type to include `inputStreamId`:

```ts
    const toolCalls = new Map<
      number,
      { id: string; name: string; arguments: string; inputStreamId: string }
    >();
```

Replace the `for (const toolCall of delta.tool_calls ?? [])` body in `createChatCompletionTurn` with:

```ts
          const index = Number(toolCall.index ?? 0);
          const inputStreamId = `chat:${index}`;
          const current = toolCalls.get(index) ?? {
            id: "",
            name: "",
            arguments: "",
            inputStreamId,
          };
          const argumentDelta = String(toolCall.function?.arguments ?? "");
          const nextId = String(toolCall.id ?? current.id);
          const nextProviderName = String(toolCall.function?.name ?? current.name);
          const nextArguments = `${current.arguments}${argumentDelta}`;
          toolCalls.set(index, {
            id: nextId,
            name: nextProviderName,
            arguments: nextArguments,
            inputStreamId,
          });
          if (argumentDelta) {
            yield {
              type: "tool_input_delta",
              inputStreamId,
              toolCallId: nextId || undefined,
              index,
              name: nextProviderName
                ? aithruToolName(input, nextProviderName)
                : undefined,
              delta: argumentDelta,
            };
          }
```

Then add `inputStreamId` to the final `tool_call` yield:

```ts
        inputStreamId: toolCall.inputStreamId,
```

- [ ] **Step 7: Emit OpenAI Responses deltas**

In `createResponsesTurn`, change the map type to:

```ts
    const toolCalls = new Map<
      string,
      { id: string; name: string; arguments: string; inputStreamId: string }
    >();
```

Add this branch before `response.function_call_arguments.done`:

```ts
      } else if (event.type === "response.function_call_arguments.delta") {
        const inputStreamId = String(event.item_id);
        const current = toolCalls.get(inputStreamId) ?? {
          id: "",
          name: "",
          arguments: "",
          inputStreamId,
        };
        const argumentDelta = String(event.delta ?? "");
        toolCalls.set(inputStreamId, {
          ...current,
          arguments: `${current.arguments}${argumentDelta}`,
        });
        if (argumentDelta) {
          yield {
            type: "tool_input_delta",
            inputStreamId,
            toolCallId: current.id || undefined,
            index: undefined,
            name: current.name ? aithruToolName(input, current.name) : undefined,
            delta: argumentDelta,
          };
        }
```

Update `response.function_call_arguments.done` to preserve the same stream id:

```ts
        const inputStreamId = String(event.item_id);
        const current = toolCalls.get(inputStreamId) ?? {
          id: "",
          name: "",
          arguments: "",
          inputStreamId,
        };
        toolCalls.set(inputStreamId, {
          id: String((event as any).call_id ?? current.id ?? event.item_id),
          name: String(event.name ?? current.name),
          arguments: String(event.arguments ?? current.arguments),
          inputStreamId,
        });
```

Update `response.output_item.done` to preserve item id and call id:

```ts
        const inputStreamId = String(event.item.id ?? event.item.call_id);
        const current = toolCalls.get(inputStreamId) ?? {
          id: "",
          name: "",
          arguments: "",
          inputStreamId,
        };
        toolCalls.set(inputStreamId, {
          id: String(event.item.call_id ?? event.item.id ?? current.id),
          name: String(event.item.name ?? current.name),
          arguments: String(event.item.arguments ?? current.arguments),
          inputStreamId,
        });
```

Then add `inputStreamId` to the final `tool_call` yield:

```ts
        inputStreamId: toolCall.inputStreamId,
```

- [ ] **Step 8: Align the OpenAI-compatible adapter**

In `backend/packages/model/src/provider-adapters.ts`, add the same event branch to `OpenAICompatibleAdapter.createTurn`:

```ts
      } else if (event.type === "response.function_call_arguments.delta") {
        yield {
          type: "tool_input_delta",
          inputStreamId: String(event.item_id),
          toolCallId: undefined,
          index: undefined,
          name: undefined,
          delta: String(event.delta ?? ""),
        };
```

In the existing `response.output_item.done` tool-call yield, add:

```ts
          inputStreamId: String(event.item.id ?? event.item.call_id),
```

- [ ] **Step 9: Forward deltas from the harness without executing tools**

In `backend/packages/harness/src/model-turn.ts`, add this branch before the `usage` branch:

```ts
        } else if (event.type === "tool_input_delta") {
          this.deps.eventWriter.write(
            run.id,
            currentRun.thread_id ?? null,
            EVENT_TYPES.TOOL_INPUT_DELTA,
            {
              input_stream_id: event.inputStreamId,
              tool_call_id: event.toolCallId ?? null,
              index: event.index ?? null,
              name: event.name ?? null,
              input_delta: event.delta,
            },
            { visibility: VISIBILITY.USER, source: { kind: "model" } },
          );
```

In the existing `event.type === "tool_call"` branch, pass the stream id into the run loop:

```ts
          const call = await loop.executeToolCall({
            id: event.id,
            inputStreamId: event.inputStreamId,
            name: event.name,
            input: event.input,
          });
```

- [ ] **Step 10: Carry input stream ids through `tool.proposed`**

In `backend/packages/harness/src/run-loop.ts`, extend `ToolCallStep`:

```ts
  inputStreamId?: string;
```

Replace the `EVENT_TYPES.TOOL_PROPOSED` payload with:

```ts
      {
        tool_call_id: toolCallId,
        input_stream_id: step.inputStreamId ?? null,
        name: step.name,
        input: step.input,
      },
```

- [ ] **Step 11: Run focused backend tests**

Run:

```bash
cd backend
npm run test -- tests/model/sdk-adapters.test.ts tests/model/provider-adapters.test.ts tests/model/model-turn.test.ts
```

Expected: PASS.

- [ ] **Step 12: Commit backend event plumbing**

Run:

```bash
git add backend/packages/stream/src/events.ts backend/packages/model/src/types.ts backend/packages/model/src/sdk-adapters.ts backend/packages/model/src/provider-adapters.ts backend/packages/harness/src/model-turn.ts backend/packages/harness/src/run-loop.ts backend/tests/model/sdk-adapters.test.ts backend/tests/model/provider-adapters.test.ts backend/tests/model/model-turn.test.ts
git commit -m "feat: stream tool input deltas"
```

---

### Task 2: Frontend Tool Input Draft State

**Files:**
- Modify: `frontend/src/features/chat/useRunStream.ts`
- Test: `frontend/tests/use-run-stream.test.mjs`

**Interfaces:**
- Consumes: stream events with type `tool.input_delta`.
- Produces: exported `ToolInputDraft` and `RunStreamState.toolInputDrafts`.
- Produces: reducer behavior that binds `input_stream_id` to final `tool_call_id`.

- [ ] **Step 1: Write failing reducer test**

Add `toolInputDrafts: []` to the `state()` object in `frontend/tests/use-run-stream.test.mjs`:

```js
    toolInputDrafts: [],
```

Add this test:

```js
test("reduceEvent accumulates and binds streamed tool input drafts", async () => {
  const { buildRunStreamState } = await loadRunStreamModule();
  const projected = buildRunStreamState([
    event(
      "tool.input_delta",
      {
        input_stream_id: "chat:0",
        tool_call_id: "call_1",
        index: 0,
        name: "workspace.write_file",
        input_delta: '{"path":"/outputs/live.md"',
      },
      10,
    ),
    event(
      "tool.input_delta",
      {
        input_stream_id: "chat:0",
        tool_call_id: "call_1",
        index: 0,
        name: "workspace.write_file",
        input_delta: ',"content":"Hello',
      },
      11,
    ),
    event(
      "tool.proposed",
      {
        input_stream_id: "chat:0",
        tool_call_id: "call_1",
        name: "workspace.write_file",
        input: { path: "/outputs/live.md", content: "Hello" },
      },
      12,
    ),
    event(
      "tool.completed",
      {
        tool_call_id: "call_1",
        name: "workspace.write_file",
        output: { path: "/outputs/live.md", version: 1 },
      },
      13,
    ),
  ]);

  assert.deepEqual(projected.toolInputDrafts, [
    {
      inputStreamId: "chat:0",
      toolCallId: "call_1",
      toolName: "workspace.write_file",
      inputText: '{"path":"/outputs/live.md","content":"Hello',
      status: "completed",
      sequence: 10,
      lastSequence: 13,
      createdAt: "2026-06-23T00:00:00.000Z",
      updatedAt: "2026-06-23T00:00:00.000Z",
    },
  ]);
});
```

- [ ] **Step 2: Run reducer test to verify it fails**

Run:

```bash
cd frontend
npm test -- tests/use-run-stream.test.mjs
```

Expected: FAIL because `toolInputDrafts` is not projected.

- [ ] **Step 3: Add draft state types and initial state**

In `frontend/src/features/chat/useRunStream.ts`, add:

```ts
export interface ToolInputDraft {
  inputStreamId: string;
  toolCallId?: string;
  toolName?: string;
  inputText: string;
  status: "streaming" | "proposed" | "completed" | "failed" | "denied";
  sequence?: number;
  lastSequence?: number;
  createdAt?: string;
  updatedAt?: string;
}
```

Add this field to `RunStreamState`:

```ts
  toolInputDrafts: ToolInputDraft[];
```

Add this value wherever the initial state object is created:

```ts
  toolInputDrafts: [],
```

- [ ] **Step 4: Add reducer helpers**

In `frontend/src/features/chat/useRunStream.ts`, near the other reducer helper functions, add:

```ts
function stringPayload(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function numberPayload(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function applyToolInputDelta(
  drafts: ToolInputDraft[],
  event: AgentStreamEvent,
): ToolInputDraft[] {
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  const inputStreamId = stringPayload(payload.input_stream_id);
  const delta = stringPayload(payload.input_delta);
  if (!inputStreamId || !delta) return drafts;

  const existing = drafts.find((draft) => draft.inputStreamId === inputStreamId);
  const patch: ToolInputDraft = {
    inputStreamId,
    toolCallId: stringPayload(payload.tool_call_id) ?? existing?.toolCallId,
    toolName: stringPayload(payload.name) ?? existing?.toolName,
    inputText: `${existing?.inputText ?? ""}${delta}`,
    status: existing?.status ?? "streaming",
    sequence: existing?.sequence ?? sequenceOf(event),
    lastSequence: sequenceOf(event),
    createdAt: existing?.createdAt ?? event.timestamp,
    updatedAt: event.timestamp,
  };

  return existing
    ? drafts.map((draft) => (draft.inputStreamId === inputStreamId ? patch : draft))
    : [...drafts, patch];
}

function bindToolInputDraft(
  drafts: ToolInputDraft[],
  event: AgentStreamEvent,
  status: ToolInputDraft["status"],
): ToolInputDraft[] {
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  const inputStreamId = stringPayload(payload.input_stream_id);
  const toolCallId = stringPayload(payload.tool_call_id);
  if (!inputStreamId && !toolCallId) return drafts;

  return drafts.map((draft) => {
    const matches =
      (inputStreamId && draft.inputStreamId === inputStreamId) ||
      (toolCallId && draft.toolCallId === toolCallId);
    if (!matches) return draft;
    return {
      ...draft,
      toolCallId: toolCallId ?? draft.toolCallId,
      toolName: stringPayload(payload.name) ?? stringPayload(payload.tool_name) ?? draft.toolName,
      status,
      lastSequence: sequenceOf(event),
      updatedAt: event.timestamp,
    };
  });
}
```

- [ ] **Step 5: Handle `tool.input_delta` and bind statuses**

In `reduceEvent`, add this case before the tool lifecycle cases:

```ts
    case "tool.input_delta": {
      return {
        ...state,
        toolInputDrafts: applyToolInputDelta(state.toolInputDrafts ?? [], event),
      };
    }
```

In the existing tool lifecycle case, after computing `patch`, compute:

```ts
      const nextToolInputDrafts =
        type === "tool.proposed"
          ? bindToolInputDraft(state.toolInputDrafts ?? [], event, "proposed")
          : type === "tool.completed"
            ? bindToolInputDraft(state.toolInputDrafts ?? [], event, "completed")
            : type === "tool.failed"
              ? bindToolInputDraft(state.toolInputDrafts ?? [], event, "failed")
              : type === "tool.denied"
                ? bindToolInputDraft(state.toolInputDrafts ?? [], event, "denied")
                : state.toolInputDrafts ?? [];
```

Include `toolInputDrafts: nextToolInputDrafts` in both return branches for existing and new tool calls.

- [ ] **Step 6: Run frontend reducer test**

Run:

```bash
cd frontend
npm test -- tests/use-run-stream.test.mjs
```

Expected: PASS.

- [ ] **Step 7: Commit frontend reducer state**

Run:

```bash
git add frontend/src/features/chat/useRunStream.ts frontend/tests/use-run-stream.test.mjs
git commit -m "feat: track streamed tool input drafts"
```

---

### Task 3: Draft Workspace File Projection

**Files:**
- Modify: `frontend/src/features/inspection/runFilesView.ts`
- Test: `frontend/tests/run-files-view.test.mjs`

**Interfaces:**
- Consumes: `ToolInputDraft`-like objects with `inputStreamId`, `toolCallId`, `toolName`, `inputText`, `status`, and `lastSequence`.
- Produces: `buildDraftWorkspaceFiles(toolInputDrafts)`.
- Produces: draft-aware `RunFileView` objects with `isDraft`, `draftContent`, and `draftRevision`.

- [ ] **Step 1: Write failing draft projection tests**

Add these tests to `frontend/tests/run-files-view.test.mjs`:

```js
test("buildDraftWorkspaceFiles extracts workspace write_file partial content", async () => {
  const { buildDraftWorkspaceFiles } = await loadRunFilesView();
  const drafts = buildDraftWorkspaceFiles([
    {
      inputStreamId: "chat:0",
      toolCallId: "call_1",
      toolName: "workspace.write_file",
      inputText: '{"path":"/outputs/live.html","content":"<h1>Hello',
      status: "streaming",
      lastSequence: 11,
    },
  ]);

  assert.deepEqual(drafts, [
    {
      id: "ws-/outputs/live.html",
      path: "/outputs/live.html",
      name: "live.html",
      content: "<h1>Hello",
      sourceToolCallId: "call_1",
      sourceInputStreamId: "chat:0",
      status: "streaming",
      lastSequence: 11,
    },
  ]);
});

test("buildRunFileViews includes draft files until a real file exists", async () => {
  const { buildRunFileViews } = await loadRunFilesView();
  const draftWorkspaceFiles = [
    {
      id: "ws-/outputs/live.md",
      path: "/outputs/live.md",
      name: "live.md",
      content: "# Live",
      sourceInputStreamId: "chat:0",
      status: "streaming",
      lastSequence: 11,
    },
  ];

  const withDraft = buildRunFileViews({ draftWorkspaceFiles });
  assert.equal(withDraft.length, 1);
  assert.equal(withDraft[0].id, "ws-/outputs/live.md");
  assert.equal(withDraft[0].isDraft, true);
  assert.equal(withDraft[0].draftContent, "# Live");
  assert.equal(withDraft[0].canDownload, false);
  assert.equal(withDraft[0].previewKind, "markdown");

  const withRealFile = buildRunFileViews({
    workspaceId: "ws1",
    workspaceFiles: [{ path: "/outputs/live.md", size: 8, media_type: "text/markdown" }],
    draftWorkspaceFiles,
  });
  assert.equal(withRealFile.length, 1);
  assert.equal(withRealFile[0].isDraft, undefined);
  assert.equal(withRealFile[0].href, "/api/workspaces/ws1/files/outputs/live.md/download");
});
```

- [ ] **Step 2: Run projection tests to verify they fail**

Run:

```bash
cd frontend
npm test -- tests/run-files-view.test.mjs
```

Expected: FAIL because draft helpers and draft fields do not exist.

- [ ] **Step 3: Add draft file types to `runFilesView.ts`**

In `frontend/src/features/inspection/runFilesView.ts`, extend `RunFileView`:

```ts
  isDraft?: boolean;
  draftContent?: string;
  draftStatus?: DraftWorkspaceFileInput["status"];
  draftRevision?: string | number;
```

Add these interfaces:

```ts
export interface ToolInputDraftInput {
  inputStreamId: string;
  toolCallId?: string;
  toolName?: string;
  inputText: string;
  status: "streaming" | "proposed" | "completed" | "failed" | "denied";
  lastSequence?: number;
}

export interface DraftWorkspaceFileInput {
  id: string;
  path: string;
  name: string;
  content: string;
  sourceToolCallId?: string;
  sourceInputStreamId: string;
  status: ToolInputDraftInput["status"];
  lastSequence?: number;
}
```

Add `draftWorkspaceFiles` to `buildRunFileViews` input:

```ts
  draftWorkspaceFiles?: DraftWorkspaceFileInput[];
```

- [ ] **Step 4: Add partial JSON extraction helpers**

Add these helpers to `frontend/src/features/inspection/runFilesView.ts`:

```ts
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function decodeJsonEscape(char: string): string {
  if (char === "n") return "\n";
  if (char === "r") return "\r";
  if (char === "t") return "\t";
  if (char === '"') return '"';
  if (char === "\\") return "\\";
  return char;
}

function readJsonStringProperty(
  source: string,
  key: string,
  options: { allowUnclosed?: boolean } = {},
): string | undefined {
  const keyIndex = source.indexOf(`"${key}"`);
  if (keyIndex < 0) return undefined;
  const colonIndex = source.indexOf(":", keyIndex + key.length + 2);
  if (colonIndex < 0) return undefined;
  const quoteIndex = source.indexOf('"', colonIndex + 1);
  if (quoteIndex < 0) return undefined;

  let result = "";
  let escaped = false;
  for (let index = quoteIndex + 1; index < source.length; index += 1) {
    const char = source[index];
    if (escaped) {
      result += decodeJsonEscape(char);
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (char === '"') return result;
    result += char;
  }

  return options.allowUnclosed ? result : undefined;
}

function extractWorkspaceWriteDraft(inputText: string): { path: string; content: string } | null {
  try {
    const parsed = JSON.parse(inputText);
    if (
      isRecord(parsed) &&
      typeof parsed.path === "string" &&
      typeof parsed.content === "string"
    ) {
      return { path: parsed.path, content: parsed.content };
    }
  } catch {
    const path = readJsonStringProperty(inputText, "path");
    if (!path) return null;
    return {
      path,
      content: readJsonStringProperty(inputText, "content", { allowUnclosed: true }) ?? "",
    };
  }
  return null;
}
```

- [ ] **Step 5: Add draft projection**

Add this exported function to `frontend/src/features/inspection/runFilesView.ts`:

```ts
export function buildDraftWorkspaceFiles(
  toolInputDrafts: ToolInputDraftInput[] = [],
): DraftWorkspaceFileInput[] {
  const files: DraftWorkspaceFileInput[] = [];
  for (const draft of toolInputDrafts) {
    if (draft.toolName !== "workspace.write_file") continue;
    if (draft.status === "failed" || draft.status === "denied") continue;
    const extracted = extractWorkspaceWriteDraft(draft.inputText);
    if (!extracted) continue;
    const pathParts = extracted.path.split("/");
    const name = pathParts[pathParts.length - 1] || extracted.path;
    files.push({
      id: `ws-${extracted.path}`,
      path: extracted.path,
      name,
      content: extracted.content,
      sourceToolCallId: draft.toolCallId,
      sourceInputStreamId: draft.inputStreamId,
      status: draft.status,
      lastSequence: draft.lastSequence,
    });
  }
  return files;
}
```

- [ ] **Step 6: Include draft files in `buildRunFileViews`**

Add this helper near `outputLikePath`:

```ts
function normalizeWorkspacePath(path: string): string {
  return path.replace(/^\/+/, "");
}
```

At the start of `buildRunFileViews`, after `workspaceFiles`, add:

```ts
  const realPaths = new Set(workspaceFiles.map((f) => normalizeWorkspacePath(f.path)));
```

After the existing workspace file loop, add:

```ts
  for (const draft of input.draftWorkspaceFiles ?? []) {
    if (realPaths.has(normalizeWorkspacePath(draft.path))) continue;
    const previewKind = previewKindForFile({ name: draft.name });
    result.push({
      id: draft.id,
      kind: outputLikePath(draft.path) ? "output_file" : "modified_file",
      name: draft.name,
      path: draft.path,
      typeLabel: inferFileTypeLabel({ name: draft.name }),
      sizeLabel: formatFileSize(new TextEncoder().encode(draft.content).length),
      canDownload: false,
      canPreview: previewKind !== "unsupported" && !["image", "pdf"].includes(previewKind),
      previewKind,
      language: languageForFile(draft.name),
      isDraft: true,
      draftContent: draft.content,
      draftStatus: draft.status,
      draftRevision: draft.lastSequence ?? draft.content.length,
    });
  }
```

- [ ] **Step 7: Run projection tests**

Run:

```bash
cd frontend
npm test -- tests/run-files-view.test.mjs
```

Expected: PASS.

- [ ] **Step 8: Commit draft file projection**

Run:

```bash
git add frontend/src/features/inspection/runFilesView.ts frontend/tests/run-files-view.test.mjs
git commit -m "feat: derive draft workspace file views"
```

---

### Task 4: Draft Preview Panel And One-Shot Auto-Open

**Files:**
- Modify: `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx`
- Modify: `frontend/src/features/sidebar/panels/FileListPanel.tsx`
- Modify: `frontend/src/AppShell.tsx`
- Test: `frontend/tests/file-preview-drafts.test.mjs`
- Test: `frontend/tests/app-shell-actions.test.mjs`

**Interfaces:**
- Consumes: `DraftWorkspaceFileInput[]` from `buildDraftWorkspaceFiles`.
- Produces: preview panel rendering from `RunFileView.draftContent`.
- Produces: one-shot auto-open behavior for the first live draft file.

- [ ] **Step 1: Add source-level preview tests**

Create `frontend/tests/file-preview-drafts.test.mjs`:

```js
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const filePreviewPanelPath = new URL(
  "../src/features/sidebar/panels/FilePreviewPanel.tsx",
  import.meta.url,
);
const fileListPanelPath = new URL(
  "../src/features/sidebar/panels/FileListPanel.tsx",
  import.meta.url,
);

test("FilePreviewPanel renders draft previews without workspace fetches", async () => {
  const source = await readFile(filePreviewPanelPath, "utf8");

  assert.match(source, /draftWorkspaceFiles/);
  assert.match(source, /activeFile\.draftContent !== undefined/);
  assert.match(source, /previewFromDraftFile/);
  assert.match(source, /srcDoc=/);
  assert.match(source, /enabled: !!activeFile && activeFile\.canPreview && activeFile\.draftContent === undefined/);
});

test("FileListPanel passes draft workspace files into run file views", async () => {
  const source = await readFile(fileListPanelPath, "utf8");

  assert.match(source, /draftWorkspaceFiles/);
  assert.match(source, /buildRunFileViews\(\{/);
  assert.match(source, /draftWorkspaceFiles,/);
});
```

Add this test to `frontend/tests/app-shell-actions.test.mjs`:

```js
test("app shell derives draft workspace files and auto-opens them once", async () => {
  const source = await readFile(appShellPath, "utf8");

  assert.match(source, /buildDraftWorkspaceFiles/);
  assert.match(source, /draftWorkspaceFiles/);
  assert.match(source, /openedDraftFileIdsRef/);
  assert.match(source, /handlePreviewFile\(draft\.id\)/);
  assert.match(source, /draftWorkspaceFiles=\{draftWorkspaceFiles\}/);
});
```

- [ ] **Step 2: Run source tests to verify they fail**

Run:

```bash
cd frontend
npm test -- tests/file-preview-drafts.test.mjs tests/app-shell-actions.test.mjs
```

Expected: FAIL because draft props and auto-open wiring do not exist.

- [ ] **Step 3: Make `FilePreviewPanel` draft-aware**

In `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx`, import the draft type:

```ts
  type DraftWorkspaceFileInput,
```

Add this prop:

```ts
  draftWorkspaceFiles?: DraftWorkspaceFileInput[];
```

Add it to the component parameters:

```ts
  draftWorkspaceFiles = [],
```

Pass it into `buildRunFileViews`:

```ts
    draftWorkspaceFiles,
```

Change the preview query `enabled` line to:

```ts
    enabled: !!activeFile && activeFile.canPreview && activeFile.draftContent === undefined,
```

Add this helper before `readFilePreview`:

```ts
function previewFromDraftFile(file: RunFileView): FilePreviewData | null {
  if (file.draftContent === undefined) return null;
  return {
    kind: file.previewKind,
    mediaType: null,
    content: file.draftContent,
  };
}
```

After `previewQuery`, add:

```ts
  const draftPreview = activeFile ? previewFromDraftFile(activeFile) : null;
```

In the preview content block, render `draftPreview` before query states:

```tsx
        {draftPreview && <PreviewBody file={activeFile} preview={draftPreview} />}
        {!draftPreview && previewQuery.isLoading && <LoadingState />}
        {!draftPreview && previewQuery.error && (
          <ErrorState error={previewQuery.error} onRetry={() => previewQuery.refetch()} />
        )}
        {!draftPreview && !previewQuery.isLoading && !previewQuery.error && previewQuery.data && (
          <PreviewBody file={activeFile} preview={previewQuery.data} />
        )}
        {!draftPreview && !previewQuery.isLoading && !previewQuery.error && !previewQuery.data && (
          <EmptyState
            title={t("chat:files.previewUnavailable", "Preview unavailable")}
            description={t("chat:files.previewUnavailableDescription", "Download this file to open it locally.")}
          />
        )}
```

In `PreviewBody`, handle draft HTML before URL HTML:

```tsx
  if (preview.kind === "html" && preview.content !== undefined) {
    return (
      <iframe
        title={file.name}
        srcDoc={preview.content}
        sandbox="allow-scripts"
        className="h-full min-h-[520px] w-full rounded-md border bg-background"
      />
    );
  }
```

- [ ] **Step 4: Pass drafts through `FileListPanel`**

In `frontend/src/features/sidebar/panels/FileListPanel.tsx`, import the draft type:

```ts
import { buildRunFileViews, type DraftWorkspaceFileInput, type RunFileView } from "@/features/inspection/runFilesView";
```

Add this prop:

```ts
  draftWorkspaceFiles?: DraftWorkspaceFileInput[];
```

Change the component signature:

```ts
export function FileListPanel({
  runId,
  workspaceId,
  draftWorkspaceFiles = [],
  onSelectFile,
  onClose,
}: FileListPanelProps) {
```

Pass drafts into `buildRunFileViews`:

```ts
    draftWorkspaceFiles,
```

- [ ] **Step 5: Derive and auto-open drafts in `AppShell`**

In `frontend/src/AppShell.tsx`, update the import:

```ts
import { buildDraftWorkspaceFiles } from "@/features/inspection/runFilesView";
```

After `const { state: streamState } = useRunStream(activeRunId);`, add:

```ts
  const draftWorkspaceFiles = React.useMemo(
    () => buildDraftWorkspaceFiles(streamState.toolInputDrafts ?? []),
    [streamState.toolInputDrafts],
  );
  const openedDraftFileIdsRef = React.useRef<Set<string>>(new Set());
```

Wrap `handlePreviewFile` in `React.useCallback`:

```ts
  const handlePreviewFile = React.useCallback((fileId: string) => {
    onOpenFileIdsChange(
      openFileIds.includes(fileId) ? openFileIds : [...openFileIds, fileId],
    );
    onActiveFileIdChange(fileId);
    onRightPanelChange("preview");
  }, [onActiveFileIdChange, onOpenFileIdsChange, onRightPanelChange, openFileIds]);
```

Then add the one-shot auto-open effect:

```ts
  React.useEffect(() => {
    const draft = draftWorkspaceFiles.find(
      (file) => file.content.length > 0 && !openedDraftFileIdsRef.current.has(file.id),
    );
    if (!draft) return;
    openedDraftFileIdsRef.current.add(draft.id);
    handlePreviewFile(draft.id);
  }, [draftWorkspaceFiles, handlePreviewFile]);
```

Pass drafts into both panels:

```tsx
          draftWorkspaceFiles={draftWorkspaceFiles}
```

- [ ] **Step 6: Run focused frontend tests**

Run:

```bash
cd frontend
npm test -- tests/file-preview-drafts.test.mjs tests/app-shell-actions.test.mjs tests/run-files-view.test.mjs tests/use-run-stream.test.mjs
```

Expected: PASS.

- [ ] **Step 7: Commit preview wiring**

Run:

```bash
git add frontend/src/features/sidebar/panels/FilePreviewPanel.tsx frontend/src/features/sidebar/panels/FileListPanel.tsx frontend/src/AppShell.tsx frontend/tests/file-preview-drafts.test.mjs frontend/tests/app-shell-actions.test.mjs
git commit -m "feat: preview streamed write_file drafts"
```

---

### Task 5: Full Verification

**Files:**
- No source files unless a focused test reveals a broken assertion from earlier tasks.

**Interfaces:**
- Consumes: all completed tasks.
- Produces: verified implementation ready for review.

- [ ] **Step 1: Run backend verification**

Run:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

Expected: all commands exit 0.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
cd frontend
npm run typecheck
npm test
```

Expected: both commands exit 0.

- [ ] **Step 3: Inspect final diff**

Run:

```bash
git status --short
git log --oneline -5
```

Expected: working tree is clean after the task commits, and recent commits include:

```txt
feat: stream tool input deltas
feat: track streamed tool input drafts
feat: derive draft workspace file views
feat: preview streamed write_file drafts
```

If the implementer chose to squash, working tree must still be clean and the squashed commit message must mention tool input streaming and draft previews.

---

## Self-Review

Spec coverage:

- Generic `tool.input_delta` event: Task 1.
- Provider adapter support for OpenAI Chat and Responses: Task 1.
- Harness forwarding without execution: Task 1.
- Frontend draft state and replay: Task 2.
- `workspace.write_file` draft file projection: Task 3.
- Preview panel rendering and real-file replacement: Tasks 3 and 4.
- One-shot frontend open behavior: Task 4.
- Approval boundary preservation: Task 1 harness test and Task 5 full backend verification.
- Anthropic input streaming is intentionally excluded from implementation, matching the spec rollout.

Type consistency:

- Backend model event uses camelCase: `inputStreamId`, `toolCallId`.
- Stream payload uses snake case: `input_stream_id`, `tool_call_id`, `input_delta`.
- Frontend draft state uses camelCase and is derived from snake-case stream payload.
- File preview ids remain `ws-${path}`.

No new dependencies are required.
