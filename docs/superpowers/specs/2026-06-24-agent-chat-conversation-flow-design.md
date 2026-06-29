# Agent Chat Conversation Flow Design

## Goal

Redesign the in-run chat display so user messages, assistant process, tool calls,
real thinking content, and final answers read as one quiet conversation flow.

## Principles

- User messages are right-aligned bubbles.
- Assistant output is left-aligned prose without avatars.
- Thinking, tool calls, and final answers share the same assistant alignment.
- Real thinking content is shown only when the stream provides it.
- Tool calls can appear between thinking segments.
- Run completion is a lightweight footer, not a card.
- Trace, token, and tool details are available but visually secondary.

## Conversation Shape

```txt
                                      User bubble

Thought for 18s · Used 2 tools >
  Real provider thinking content, when available.

  Tool workspace.list_files      Completed
  Tool workspace.read_file       Completed

Assistant final answer prose.

Completed · 4,403 tokens · View trace
```

## Data Shape

The frontend projects run events into a display timeline. Current events provide
messages, model timing, tool calls, inline requests, and token usage. The display
must also tolerate future reasoning events without inventing content.

Future reasoning payloads may arrive as:

- `reasoning.delta`
- `thinking.delta`
- `message.reasoning.delta`
- `message.thinking.delta`

Each reasoning segment is ordered by stream sequence and rendered inside the
assistant process disclosure.

## Component Design

- `chatTimeline.ts` builds ordered message/process/completion items.
- `ChatPanel.tsx` renders user bubbles, assistant prose, and one lightweight
  assistant process disclosure per run.
- Reasoning content renders directly under the process summary without a
  repeated "Thinking" subheading.
- `ToolCallCard.tsx` becomes a compact inline tool row with expandable details.
- `AgentActivityCard.tsx` no longer owns the main chat process UI.

## Verification

- Frontend unit tests cover event ordering and reasoning/tool interleaving.
- Typecheck must pass.
- Browser check must verify no avatars, aligned content, compact tools, and a
  lightweight completion footer.
