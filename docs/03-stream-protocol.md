# Agent Stream Protocol

Status: target protocol

This document defines the Aithru Agent stream protocol.

The stream is not a plain token stream. It is a structured, replayable, append-only run event stream that can drive chat UI, run timeline UI, workspace UI, artifact UI, approval UI, debug trace, and audit projection.

## One-line definition

```txt
Agent Stream = Chat output + Harness runtime events + Trace events + UI state updates as one structured event stream.
```

## Goals

The stream protocol must support:

- ChatGPT-style assistant text streaming;
- Codex/Claude Code-style tool and file progress;
- DeerFlow-like todos, workspace, subagents, sandbox, memory, and artifacts;
- approval pause/resume;
- cancellation;
- replay and reconnect;
- multiple observers of the same run;
- Workbench node trace consumption;
- Platform audit and redaction boundaries.

## Non-goals

The stream protocol is not:

- a raw token-only stream;
- a best-effort log string;
- a replacement for durable event storage;
- a browser-only protocol;
- a workflow event protocol for `WorkflowSpec` runs.

Workbench workflow events remain Workbench/Core events. Agent stream events describe Agent harness runs.

## Transport recommendation

V1 should use Server-Sent Events:

```txt
GET /api/runs/:runId/events/stream?afterSequence=123
```

Reasons:

- primary direction is server-to-client;
- HTTP-friendly;
- easy to use from Platform hosted app iframes;
- supports reconnect with `Last-Event-ID`;
- reverse operations can use REST endpoints;
- easier to proxy and inspect than WebSocket.

Reverse operations should be REST:

```txt
POST /api/runs/:runId/cancel
POST /api/runs/:runId/input
POST /api/runs/:runId/resume
POST /api/approvals/:approvalId/resolve
```

WebSocket can be added later for collaborative, terminal-like, or interactive bidirectional sessions.

## Event storage rule

Events must be persisted before they are published.

```txt
Harness creates event
  -> EventStore.append(event)
  -> EventBus.publish(persistedEvent)
  -> SSE clients receive persistedEvent
```

Do not publish first and persist later. Replay, audit, reconnect, and Workbench trace integration depend on durable ordering.

## Event envelope

All events use one envelope.

```ts
type AgentStreamEvent = {
  id: string;
  runId: string;
  threadId?: string;
  sequence: number;
  timestamp: string;

  type: AgentStreamEventType;

  source: {
    kind:
      | "harness"
      | "model"
      | "tool"
      | "subagent"
      | "sandbox"
      | "workspace"
      | "memory"
      | "web"
      | "approval"
      | "system";
    id?: string;
    name?: string;
  };

  visibility: "user" | "debug" | "audit";
  redaction: "none" | "partial" | "full";

  summary?: string;
  payload: unknown;
};
```

Rules:

- `sequence` is strictly increasing within one run.
- `id` is globally unique.
- `timestamp` is server-generated.
- `visibility=user` is safe for normal UI.
- `visibility=debug` may include technical details but no secrets.
- `visibility=audit` may include governance metadata for audit stores.
- `redaction` describes whether the payload was redacted before storage/display.

## SSE wire format

Normal event:

```txt
id: run_123:42
event: agent.event
data: {"runId":"run_123","sequence":42,"type":"todo.updated","timestamp":"...","payload":{}}
```

Heartbeat:

```txt
event: heartbeat
data: {"runId":"run_123","timestamp":"..."}
```

Terminal event:

```txt
event: run.terminal
data: {"runId":"run_123","status":"completed","sequence":128}
```

The stream may close after terminal event.

## Reconnect and replay

The server must support both:

```txt
GET /api/runs/:runId/events/stream?afterSequence=42
```

and:

```txt
Last-Event-ID: run_123:42
```

Server behavior:

1. Parse `afterSequence` or `Last-Event-ID`.
2. Read historical events after that sequence from `EventStore`.
3. Send historical events in sequence order.
4. Attach the client to live `EventBus`.
5. On terminal run status, send `run.terminal` and close.

## Event type groups

### Run lifecycle

```txt
run.created
run.queued
run.started
run.paused
run.resumed
run.completed
run.failed
run.cancelled
```

Example payload:

```json
{
  "status": "running",
  "source": "chat",
  "skillId": "skill_pr_reviewer",
  "workspaceId": "ws_123"
}
```

### Message events

```txt
message.created
message.delta
message.completed
message.failed
```

`message.delta` is user-facing assistant output.

```json
{
  "messageId": "msg_123",
  "role": "assistant",
  "delta": "我先帮你拆解任务："
}
```

`message.completed` should reference or include the complete content.

```json
{
  "messageId": "msg_123",
  "role": "assistant",
  "contentRef": "message_content_123"
}
```

### Todo / runtime plan events

```txt
todo.created
todo.updated
todo.completed
todo.blocked
todo.cancelled
```

```json
{
  "todoId": "todo_1",
  "title": "读取项目文档",
  "status": "running",
  "order": 1
}
```

Todos are runtime state and must not be treated as Workbench nodes.

### Model events

```txt
model.started
model.delta
model.completed
model.failed
```

Model raw deltas should normally be debug visibility. User-facing assistant text should be emitted as `message.delta`.

`model.completed` is emitted when the model loop finishes normally (after all model results are consumed, including after approval resume).

`model.failed` is emitted when the model iterator throws an error. Must appear before `run.failed`.

During an approval pause, the model iterator is saved but no `model.completed` is emitted until the run resumes and the iterator finishes. If the run is rejected, the model span is implicitly terminated by `run.failed`.

```json
{
  "model": "openai-compatible:deepseek-chat",
  "usage": {
    "inputTokens": 1200,
    "outputTokens": 300
  }
}
```

### Tool events

```txt
tool.proposed
tool.started
tool.completed
tool.failed
tool.denied
```

`tool.proposed` means the model proposed a tool call.

`tool.started` means policy and approval checks passed and **real execution is about to begin**. Approval must not happen after `tool.started`.

Terminal `tool.completed`, `tool.failed`, and `tool.denied` events may carry
Pydantic governance payloads:

- `authorization_decision`: safe actor/scope decision metadata;
- `audit`: capability audit metadata serialized with
  `authorization_decision`, not the sensitive key `authorization`.

These payloads let replay, trace, and capability-audit APIs inspect tool policy
outcomes without exposing raw credentials or bypassing stream redaction.

#### Safe/read tool event order (no approval needed)

```
tool.proposed  ← model proposed the call
tool.started   ← prepareToolCall returned "ready", execution imminent
tool.completed ← executeToolCall finished
```

#### Write/dangerous tool event order (approval needed)

```
tool.proposed       ← model proposed the call
approval.requested  ← prepareToolCall returned "waiting_approval"
run.paused          ← run is paused, harness stores pending approval
...
approval.resolved   ← human or policy resolved the approval
run.resumed         ← run continues
tool.started        ← executeToolCall begins (with alreadyApproved=true)
tool.completed      ← executeToolCall finished
```

`tool.started` must never be emitted before approval. The approval workflow must validate that `tool.started` is not present in the event stream for any tool that goes through an approval gate.

```json
{
  "toolCallId": "toolcall_123",
  "toolName": "workspace.writeFile",
  "riskLevel": "write",
  "summary": "写入 /reports/analysis.md"
}
```

### Context events

```txt
context.packet.built
```

This debug event is emitted when the native harness builds a non-empty
Pydantic `AgentRunContextPacket` for model context engineering. The event
summarizes counts, budget usage, dropped-context counts, and truncation state
only; the full prompt text is not copied into the stream. Context packets are
internal harness projections over existing thread messages, runtime todos,
artifacts, prior `tool.completed` result summaries, scoped memory recall, and
resume-state hints. They are not WorkflowSpec objects or public API contracts.

```json
{
  "thread_messages": 1,
  "todos": 1,
  "artifacts": 1,
  "tool_results": 1,
  "memory": 1,
  "has_truncated_content": false,
  "has_dropped_context": false,
  "budget": {
    "max_chars": 6000,
    "used_chars": 214,
    "remaining_chars": 5786,
    "dropped_thread_messages": 0,
    "dropped_todos": 0,
    "dropped_artifacts": 0,
    "dropped_tool_results": 0,
    "dropped_memory": 0,
    "truncated_items": 0
  }
}
```

### Web events

```txt
web.search.completed
web.fetch.completed
web.search.failed
web.fetch.failed
```

These events summarize controlled web provider work for research timelines and
trace projection. Completed events are emitted after the corresponding
capability router tool call succeeds. Failed events are emitted for controlled
provider failures and should carry the tool call id, the query or URL reference,
sanitized error payload, and a structured research limitation payload when the
failure can affect report quality. Fetch events should not duplicate the full
fetched body.

For controlled web failures, the tool bridge may also return a model-visible
recoverable payload such as `{ "status": "failed", "recoverable": true, ... }`
instead of raising a run-failing exception when the tool descriptor's
`failure_policy` is `return_recoverable`. The stream must still include the
dedicated `web.*.failed` event and the generic `tool.failed` event so UI, trace,
and audit projections do not lose the failed tool call.

```json
{
  "toolCallId": "toolcall_web_fetch",
  "url": "https://example.com/source",
  "statusCode": 200,
  "mediaType": "text/html; charset=utf-8",
  "contentLength": 12042,
  "truncated": false
}
```

```json
{
  "toolCallId": "toolcall_web_search",
  "query": "aithru deerflow parity",
  "error": {
    "message": "search provider unavailable"
  },
  "limitation": {
    "code": "web_search_failed",
    "severity": "warning",
    "message": "Controlled web search failed for `aithru deerflow parity`: search provider unavailable.",
    "source_url": null
  }
}
```

### Approval events

```txt
approval.requested
approval.resolved
approval.expired
```

```json
{
  "approvalId": "appr_123",
  "toolCallId": "toolcall_123",
  "reason": "Agent 请求执行 sandbox.runPython",
  "riskLevel": "dangerous",
  "redactedInput": {
    "command": "python analysis.py",
    "workspace": "/sandbox/run_123"
  }
}
```

After `approval.requested`, run status should become `waiting_approval` or `run.paused` should be emitted.

When resolved:

```txt
approval.resolved
run.resumed
tool.started
```

or if rejected:

```txt
approval.resolved
run.failed
```

### Input events

```txt
input.requested
input.received
```

`input.requested` is emitted when an agent calls `input.request` and the harness
pauses the run as `waiting_input`. `input.received` is emitted after
`POST /api/runs/:runId/input` persists the user message for a waiting run. The
run can then emit `run.resumed` with `status: "queued"` and continue through the
ordinary worker queue.

```json
{
  "input_request_id": "toolcall_input",
  "tool_call_id": "toolcall_input",
  "prompt": "Which region should I use?",
  "reason": "The report needs a geographic scope."
}
```

### Workspace events

```txt
workspace.file.created
workspace.file.updated
workspace.file.deleted
workspace.file.diff
workspace.snapshot.created
```

```json
{
  "workspaceId": "ws_123",
  "path": "/reports/sales-analysis.md",
  "operation": "write",
  "size": 18432,
  "artifactCandidate": true
}
```

Workspace events drive file tree UI and run trace UI.

### Artifact events

```txt
artifact.created
artifact.updated
artifact.finalized
artifact.exported
```

```json
{
  "artifactId": "art_123",
  "type": "report",
  "name": "销售分析报告.md",
  "workspacePath": "/reports/sales-analysis.md"
}
```

Workflow draft artifact:

```json
{
  "artifactId": "art_456",
  "type": "workflow_draft",
  "name": "销售分析自动化流程",
  "actions": ["open_in_workbench", "download_json"]
}
```

### Subagent events

```txt
subagent.started
subagent.message
subagent.todo.updated
subagent.completed
subagent.failed
```

```json
{
  "subagentRunId": "subrun_123",
  "name": "researcher",
  "task": "检索相关资料并提取事实"
}
```

Subagent events should be visible in the parent run stream as a projection. Subagents may also have their own nested run stream in later versions.

### Sandbox events

```txt
sandbox.started
sandbox.stdout
sandbox.stderr
sandbox.file.changed
sandbox.completed
sandbox.failed
```

```json
{
  "sandboxRunId": "sandbox_123",
  "language": "python",
  "status": "running"
}
```

Stdout/stderr delta:

```json
{
  "sandboxRunId": "sandbox_123",
  "stream": "stdout",
  "delta": "Loaded 1200 rows\n"
}
```

### Memory events

```txt
memory.read
memory.written
memory.skipped
```

Memory events are normally debug or audit visibility. User UI may show summaries only.

```json
{
  "memoryScope": "project",
  "operation": "read",
  "count": 3
}
```

## Projections

One event stream should drive multiple UI projections.

| Projection | Consumes |
| --- | --- |
| Chat | `message.*`, selected `run.*`, selected `artifact.*`, selected `approval.*` |
| Run timeline | `run.*`, `todo.*`, `tool.*`, `web.*`, `subagent.*`, `sandbox.*` |
| Workspace | `workspace.*`, selected `artifact.*` |
| Artifact panel | `artifact.*` |
| Approval panel | `approval.*`, related `tool.*` |
| Debug trace | all debug-safe events |
| Audit | audit visibility events and external audit sink |

## Filtering

The stream endpoint may support filters:

```txt
?visibility=user
?types=message.delta,artifact.created,approval.requested
```

Default UI should use `visibility=user`. Developer trace may request `debug`. Audit sinks may receive `audit` through server-side integration, not browser UI by default.

## Event compaction

Token/message deltas and sandbox stdout may be high volume.

The system may compact event storage later, but must preserve replay semantics:

- retain full completed message;
- retain final tool result summary;
- retain artifact references;
- retain approval records;
- retain enough trace for audit and debug;
- preserve sequence monotonicity.

## Error handling

A failed operation should emit structured failure events, not only close the connection.

Examples:

```txt
tool.failed
sandbox.failed
model.failed
run.failed
```

Only transport errors should break the SSE connection without a terminal run event.

## Minimal implementation requirements

The first implementation must support:

- `run.created`;
- `run.started`;
- `message.created`;
- `message.delta`;
- `message.completed`;
- `todo.created`;
- `todo.updated`;
- `tool.proposed`;
- `tool.completed` or `tool.failed`;
- `workspace.file.created` or `workspace.file.updated`;
- `artifact.created`;
- `run.completed` or `run.failed`;
- replay with `afterSequence`.

Approval, sandbox, subagent, and memory events may be no-op/fake in early implementation, but their event shapes should be reserved from the beginning.

## Acceptance criteria

- Stream is structured JSON, not text-only.
- Events are persisted before publish.
- Sequence is strictly increasing per run.
- Frontend can reconnect and replay.
- Chat output and harness progress share one stream.
- Workspace/artifact/approval/subagent/sandbox events fit the same envelope.
- Sensitive values can be redacted by event visibility and redaction metadata.
