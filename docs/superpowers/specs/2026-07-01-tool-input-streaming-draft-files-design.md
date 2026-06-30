# Tool Input Streaming And Draft File Preview Design

Date: 2026-07-01
Status: approved design

## Problem

When the model writes a large workspace file through `workspace.write_file`,
the frontend can stay quiet for a long time. The expensive part is usually not
the actual file write. It is the model generating a large tool-call JSON
argument, especially the `content` string.

Today the backend buffers provider tool-call arguments until they are complete:

- OpenAI Chat Completions receives `delta.tool_calls`, but the adapter only
  emits a complete `tool_call` after the provider stream ends.
- OpenAI Responses only handles completed function-call arguments.
- The harness only emits `tool.proposed` once the full input is parsed.
- The frontend stores only tool summaries, not streamed raw tool input.

This means the user cannot see that a file is being produced until the model has
finished generating the entire `workspace.write_file` input.

## Decision

Add a generic tool-input streaming event and project `workspace.write_file`
inputs into draft workspace file previews.

The design has two layers:

```txt
generic stream layer:
  provider tool argument chunks
    -> model adapter
    -> tool.input_delta
    -> frontend tool input draft state

workspace file projection:
  streamed workspace.write_file input
    -> draft workspace file view
    -> preview panel
    -> real workspace file after approval and execution
```

Do not add file-system watching. The file may not exist while the model is
still generating the tool input.

## Non-Goals

- Do not execute tools from streamed partial inputs.
- Do not bypass capability routing, policy checks, or approvals.
- Do not let models directly create frontend artifacts or arbitrary UI state.
- Do not add a general artifact system for this feature.
- Do not add `append` or `workspace.append_file` in the first implementation.
- Do not add provider-specific event shapes to frontend state.
- Do not expose unrestricted local files, browser automation, network calls, or
  platform credentials.

## References

DeerFlow creates a draft preview from `write_file` tool-call arguments instead
of reading a partially written file:

- `frontend/src/core/artifacts/preview.ts`
- `frontend/src/core/artifacts/loader.ts`
- `backend/packages/harness/deerflow/sandbox/tools.py`

LangChain and LangGraph expose tool-call chunks through message streaming.
OpenAI Responses and Anthropic also support streamed tool argument deltas.

## Stream Event Contract

Add one event type:

```ts
TOOL_INPUT_DELTA: "tool.input_delta"
```

Payload:

```ts
type ToolInputDeltaPayload = {
  input_stream_id: string;
  tool_call_id?: string | null;
  index?: number | null;
  name?: string | null;
  input_delta: string;
};
```

Rules:

- `input_stream_id` is the stable id used to accumulate partial input.
- `tool_call_id` is present only when the provider already exposes the final
  tool call id.
- `index` is provider adapter metadata for parallel tool calls in one turn.
- `name` is the Aithru tool name when known.
- `input_delta` is the raw argument text delta.
- The event is user-visible because the same input will be user-visible at
  `tool.proposed`, but it is still a draft and must not trigger execution.

The complete tool call remains:

```ts
type ModelToolCallEvent = {
  type: "tool_call";
  id: string;
  input_stream_id?: string;
  name: string;
  input: Record<string, unknown>;
};
```

`input_stream_id` lets the frontend merge the draft with the final
`tool.proposed` call even when a provider uses different ids for streamed item
chunks and final call ids.

## Provider Adapter Behavior

Adapters normalize provider streams into Aithru events.

### OpenAI Chat Completions

For each `delta.tool_calls[]` item:

- compute `input_stream_id` from the call index, for example
  `chat:${index}`;
- update the local accumulator as it does today;
- emit `tool_input_delta` for every non-empty
  `toolCall.function.arguments` delta;
- emit the complete `tool_call` after the stream ends, with the final parsed
  input and the matching `input_stream_id`.

### OpenAI Responses

For `response.function_call_arguments.delta`:

- use `event.item_id` as `input_stream_id`;
- emit `tool_input_delta` with the delta text.

For the completed function call:

- parse the final arguments;
- emit `tool_call` with `input_stream_id` set to the same item id;
- use the final call id as the tool call id when available.

### Anthropic

Anthropic support can be added after the OpenAI path. The expected mapping is
`input_json_delta` to `tool_input_delta`. The absence of Anthropic support must
not block the generic event shape.

## Harness Behavior

`ModelTurnEvent` gains:

```ts
{
  type: "tool_input_delta";
  inputStreamId: string;
  toolCallId?: string;
  index?: number;
  name?: string;
  delta: string;
}
```

`ModelTurnLoop` handles it by writing a stream event only:

```txt
tool_input_delta
  -> eventWriter.write(TOOL_INPUT_DELTA, payload)
  -> continue model stream
```

It must not:

- call `executeToolCall`;
- create a tool call record;
- request approval;
- mutate run status;
- route through the capability router.

The existing `tool_call` event is still the only entry to policy, approval, and
execution.

## Frontend State

`RunStreamState` gains draft tool input state:

```ts
type ToolInputDraft = {
  inputStreamId: string;
  toolCallId?: string;
  toolName?: string;
  inputText: string;
  status: "streaming" | "proposed" | "completed" | "failed" | "denied";
  sequence?: number;
  lastSequence?: number;
  createdAt?: string;
  updatedAt?: string;
};
```

Reducer rules:

- `tool.input_delta` appends `input_delta` to `inputText`.
- `tool.proposed` binds `input_stream_id` to `tool_call_id` when present and
  marks the draft as `proposed`.
- `tool.completed`, `tool.failed`, and `tool.denied` update draft status when
  they reference the bound `tool_call_id`.
- Event replay must reconstruct the same draft state.

Existing `ToolCallEntry` can keep `inputSummary`. The raw draft input belongs in
`toolInputDrafts`, not the tool card summary.

## Draft Workspace File Projection

The frontend derives draft file views from tool input drafts where:

```txt
toolName == "workspace.write_file"
```

Extraction rules:

- First try `JSON.parse(inputText)`.
- If parsing fails, use a small partial JSON string extractor for `path` and
  `content`.
- Do not create a draft file until `path` is available.
- Update draft content whenever `content` grows.
- If the final tool result fails or is denied, mark the draft unavailable.
- If the real workspace file appears, the real file replaces the draft.

The derived draft file shape:

```ts
type DraftWorkspaceFile = {
  id: string;       // ws-${path}
  path: string;
  name: string;
  content: string;
  sourceToolCallId?: string;
  sourceInputStreamId: string;
  status: "streaming" | "proposed" | "completed" | "failed" | "denied";
};
```

Use `ws-${path}` as the id so existing file preview selection continues to
work. If a real workspace file with the same path exists, prefer the real file.

## Preview Panel

`FilePreviewPanel` accepts derived draft files in addition to real workspace
files.

Rules:

- `buildRunFileViews` includes draft files only when no real file exists for
  the same path.
- Draft files use the same preview kind inference as real files.
- Text, markdown, JSON, and code drafts render directly from `content`.
- HTML drafts render through `iframe srcDoc` instead of a workspace content URL.
- Image and PDF drafts are unsupported in the first implementation because the
  streamed content is plain tool input text.

`AppShell` continues to open files by id. The existing
`onPreviewFile("ws-/path")` flow does not need a new artifact id space.

## Approval And Execution Semantics

Streaming input is observational only.

```txt
tool.input_delta
  visible draft only

tool.proposed
  complete input
  policy check
  approval request when required

approval resolved
  approved -> execute real tool
  denied -> no workspace write

tool.completed
  refresh workspace files
  real file replaces draft
```

This preserves the capability boundary:

```txt
model/provider
  -> Aithru model turn loop
  -> stream observation
  -> complete tool proposal
  -> capability router
  -> policy/approval
  -> concrete workspace write
```

## Failure Handling

- Malformed partial JSON keeps accumulating without showing a draft until a
  path is extractable.
- If the model emits a different final path than the partial path, the final
  `tool.proposed` path wins.
- If the provider stream fails, draft files remain visible only as failed tool
  input state for that run.
- If a run is cancelled, draft files become unavailable.
- If event replay has no matching final `tool.proposed`, the draft stays
  `streaming` for historical inspection but does not become a real file.

## Privacy And Redaction

The first implementation emits `tool.input_delta` with the same visibility as
the eventual `tool.proposed` input. This is acceptable because the content is
already part of the user-visible tool proposal.

Future sensitive tools can opt out by marking their input fields as non-streamed
or redacted. That is outside this first feature.

## Tests

Backend:

- OpenAI Chat adapter emits `tool_input_delta` before the final `tool_call`.
- OpenAI Responses adapter maps argument deltas to the same
  `input_stream_id` as the final call.
- Harness writes `tool.input_delta` without executing tools or creating
  approvals.
- Event replay order keeps `tool.input_delta` before `tool.proposed`.

Frontend:

- Reducer accumulates `tool.input_delta` into `toolInputDrafts`.
- `tool.proposed` binds drafts to final tool calls.
- Draft file projection creates a `ws-${path}` view for `workspace.write_file`.
- Partial JSON extraction handles a growing `content` string.
- Preview panel renders draft markdown/code/text/HTML.
- Real workspace files replace drafts with the same path.

Integration:

- A run that streams a large `workspace.write_file` input opens or updates a
  draft preview before approval.
- Approving the write persists the real workspace file.
- Denying the write does not persist the file.

## Rollout

1. Add generic event and model adapter support for OpenAI providers.
2. Add harness event forwarding.
3. Add frontend draft state and reducer replay.
4. Add draft workspace file projection and preview panel support.
5. Add Anthropic input streaming later if needed.

This order keeps each step independently useful and avoids changing the
capability router until complete tool calls arrive, where it already works.
