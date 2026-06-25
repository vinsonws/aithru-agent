# Conversation Display Cards Design

## Goal

Add a controlled way for Agent runs to show rich, related cards inside the
conversation timeline, starting with files and artifacts and leaving room for
future resources such as approvals, todos, search results, memories, and
subagent outputs.

The key product rule is:

```txt
Models may request that existing resources be presented.
The harness decides which cards are valid, safe, and visible.
The frontend renders trusted card events in timeline order.
```

## Context

The current chat UI can render messages, reasoning, tool calls, completion
metadata, and the right-side file panel. It also has a file card component, but
conversation cards are not yet part of the canonical run timeline.

That leaves two risks:

- Useful results can stay hidden in tool details or side panels.
- The frontend can drift toward tool-name heuristics instead of a real product
  contract.

DeerFlow uses a pragmatic hybrid:

- it renders many tool calls by tool name in the frontend;
- it has an explicit `present_files` tool so the agent can surface output files;
- file presentation updates harness thread artifacts and the frontend renders
  those artifacts as cards.

Aithru should keep the useful part of that pattern, but make the protocol more
general and capability-bound.

References:

- DeerFlow message grouping by tool semantics:
  [frontend/src/core/messages/utils.ts](https://github.com/bytedance/deer-flow/blob/main/frontend/src/core/messages/utils.ts)
- DeerFlow message rendering:
  [frontend/src/components/workspace/messages/message-list.tsx](https://github.com/bytedance/deer-flow/blob/main/frontend/src/components/workspace/messages/message-list.tsx)
- DeerFlow `present_files` tool:
  [backend/packages/harness/deerflow/tools/builtins/present_file_tool.py](https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/tools/builtins/present_file_tool.py)
- DeerFlow artifact thread state:
  [backend/packages/harness/deerflow/agents/thread_state.py](https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/agents/thread_state.py)

## Non-Goals

- Do not let the model send arbitrary UI schemas, HTML, component names, or CSS.
- Do not make the frontend infer product cards only from raw tool names.
- Do not create Agent workflow semantics or graph behavior.
- Do not replace the trace. Cards are user-facing summaries, while trace remains
  the inspectable execution record.

## Product Shape

Cards appear inline between assistant process events and assistant text, using
the same stream ordering as reasoning and tool calls.

```txt
User asks to create a file

Thought for 3s
  Thinking
  Tool workspace.write_file

File card: a.txt

Assistant final answer

Completed
```

The inline card can also open the side panel for richer preview or actions.

## Card Contract

Cards are backend-owned domain projections. A first version can use this shape:

```txt
AgentDisplayCard
  id
  thread_id
  run_id
  sequence
  surface: conversation | side_panel | both
  type: file | artifact | approval | todo | memory | search_result | generic
  status: pending | ready | failed
  title
  summary?
  resource:
    kind
    id?
    path?
    url?
  actions[]
  source:
    created_by: harness | tool | model_request
    event_id?
    tool_call_id?
    tool_name?
  metadata?
```

Rules:

- `type` selects a trusted renderer, not a model-controlled component.
- `resource` references an existing capability-scoped resource.
- `metadata` is bounded and type-specific; it is not a freeform UI schema.
- `sequence` comes from the canonical event stream so cards preserve timeline
  order.
- `source` makes cards traceable back to the tool or event that produced them.

## Stream Events

Add canonical stream events for display cards:

```txt
display.card.created
display.card.updated
```

`display.card.created` inserts the card into the conversation timeline.
`display.card.updated` can update status, title, summary, or action state for
long-running resources.

Events should be idempotent by `card.id` and deduplicated by source event or
tool call when possible.

## Active Presentation Tool

Add a controlled tool later:

```txt
present_resources(resources, surface?)
```

Example input:

```json
{
  "surface": "conversation",
  "resources": [
    { "kind": "workspace_file", "path": "/a.txt" },
    { "kind": "artifact", "id": "artifact_123" }
  ]
}
```

This tool does not accept titles, arbitrary card types, JSX, markdown cards, or
styling. It only asks the harness to present resources that already exist.

The capability router must:

- validate the resource exists;
- validate thread, run, workspace, and scope ownership;
- apply policy and approval rules;
- redact sensitive metadata;
- emit display card events;
- return a normal tool result for traceability.

This preserves the Aithru capability boundary:

```txt
model request
  -> present_resources tool
  -> capability router
  -> policy / scope / validation
  -> display.card.created event
  -> frontend card renderer
```

## Automatic Projection

The backend can also project cards from trusted capability results without the
model explicitly calling `present_resources`.

Initial projections:

- `workspace.write_file` can produce a file card when the result is user-facing.
- artifact creation can produce an artifact card.
- approval requests can produce approval cards.
- future search, memory, todo, and subagent outputs can add their own
  projections.

The projection belongs in backend harness/capability integration, not in a
frontend tool-name switch. Frontend fallbacks may exist for legacy runs, but they
should not become the main contract.

## Frontend Rendering

Extend the chat timeline with a card item:

```txt
ChatTimelineItem
  kind: card
  card: AgentDisplayCard
```

`ChatPanel` renders card items in sequence alongside reasoning, tool calls, and
assistant text. A small registry maps trusted card types to components:

```txt
file -> DisplayFileCard
artifact -> DisplayArtifactCard
approval -> ApprovalCard
generic -> GenericDisplayCard
```

Unknown types should degrade to `GenericDisplayCard` with title, summary, and a
safe open action when available.

File and artifact cards should be clickable and open the existing right-side
preview panel. The card itself should remain useful even when the side panel is
closed.

## Persistence and API

Cards should be reconstructable from the canonical event log and available in
run/thread snapshots for reload.

Recommended first implementation:

- persist display card events in the stream event log;
- add a lightweight card projection in the run snapshot API;
- let the frontend build the timeline from stream/snapshot events.

This keeps reload behavior consistent with live streaming.

## Ordering

Cards must obey the same timeline order as reasoning, tool calls, and assistant
text.

That means a card generated after `workspace.write_file` appears after that tool
call and before later assistant text, rather than being appended at the end of
the process block.

## Safety

- Never render model-provided HTML or component names.
- Do not expose local absolute paths when a workspace-relative path is enough.
- Validate download and preview actions through the backend.
- Treat external URLs as untrusted and mark them as external actions.
- Redact sensitive fields from summaries and metadata.
- Keep cards trace-linked, so the user can inspect why a card appeared.

## Migration

Version 0 can reuse the existing file card component as `DisplayFileCard`.

For older runs without `display.card.created` events, the frontend may derive a
best-effort card from existing artifact/file snapshots. That fallback should be
temporary and should not replace backend card events.

## Verification

- Backend tests cover `present_resources` validation and display card emission.
- Stream tests verify card ordering relative to reasoning, tool calls, and text.
- API tests verify cards survive reload.
- Frontend tests verify timeline interleaving and unknown card fallback.
- Browser checks verify file cards open the side panel preview without breaking
  the inline conversation.
