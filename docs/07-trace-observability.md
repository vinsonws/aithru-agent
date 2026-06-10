# Agent Trace and Observability

Status: target architecture

## Why Not LangSmith as the Only Trace

Aithru Agent must not depend solely on LangSmith (or Langfuse, Phoenix, OTel) for trace storage because:

- **Data residency**: Enterprise deployments require on-premise or VPC-local trace storage without third-party egress.
- **Audit dependency**: Platform audit events require a local canonical trace that is available even when third-party services are unreachable.
- **Redaction boundary**: Sensitive tool inputs/outputs must be redacted before leaving the Aithru boundary. A third-party exporter receives only the already-redacted trace, never the raw event.
- **Replay**: AgentStreamEvent is replayable from the EventStore. LangSmith traces are not.
- **Cost control**: Token-level metrics and internal optimization loops should not incur per-trace SaaS costs.

Third-party services are **exporters only**. The canonical trace is Aithru-native.

## AgentStreamEvent vs AgentTraceSpan

| Concept | AgentStreamEvent | AgentTraceSpan |
| --- | --- | --- |
| Nature | Fact (append-only log) | Projection (computed view) |
| Storage | EventStore (InMemory / Postgres) | Not stored independently; always derived |
| Source of truth | Yes | No |
| Replayable | Yes — `listAfterSequence()` | No — must be re-projected |
| Contains payload | Full structured payload | Summary + span metadata + event references |
| UI use | Real-time stream | Timeline / waterfall / tree |

**Rule**: AgentStreamEvent is the system of record. AgentTraceSpan is always a projection from `projectTraceSpans(events)`.

## Trace Projection

```ts
function projectTraceSpans(events: AgentStreamEvent[]): AgentTraceSpan[]
```

The projection maps event sequences to spans:

| Event type pair | Span kind | Status |
|---|---|---|
| `run.created` → `run.completed` | `run` | `completed` |
| `run.created` → `run.failed` | `run` | `failed` |
| `run.created` → `run.cancelled` | `run` | `cancelled` |
| `model.started` → `model.completed` | `model` | `completed` |
| `model.started` → `model.failed` | `model` | `failed` |
| `tool.proposed` → `tool.completed` | `tool` | `completed` |
| `tool.proposed` → `tool.failed` | `tool` | `failed` |
| `tool.proposed` → `tool.denied` | `tool` | `failed` |
| `approval.requested` → `approval.resolved` | `approval` | `completed` |
| `workspace.file.*` | `workspace` | `completed` (instant) |
| `artifact.created` | `artifact` | `completed` (instant) |

Instant spans (workspace, artifact) are created and immediately closed — they represent single point-in-time events that do not have a duration.

## Span Types

| Kind | Description | Duration |
| --- | --- | --- |
| `run` | Full agent run lifecycle | Real (created → terminal) |
| `message` | Single message in a thread | Not yet projected |
| `model` | LLM call (with potential tool calls) | Real (started → completed/failed) |
| `tool` | Single tool execution | Real (proposed → completed/failed/denied) |
| `approval` | Approval gate pause | Real (requested → resolved) |
| `workspace` | File create/update/delete | Instant (point event) |
| `artifact` | Artifact creation | Instant (point event) |
| `subagent` | Subagent run (future) | Future |
| `sandbox` | Sandbox execution (future) | Future |
| `memory` | Memory read/write (future) | Future |

## Redaction Rules

Every span carries a `redaction` field that mirrors the originating event:

- `"none"`: safe for any UI display
- `"partial"`: some fields summarized or masked (e.g. file content preview)
- `"full"`: metadata-only, payload replaced with a redaction notice

The trace projection never de-redacts. Redaction is applied at event creation time by the capability router and workspace provider.

## Exporter Strategy

Third-party exporters are downstream consumers of the already-redacted trace:

```txt
AgentStreamEvent
  → projectTraceSpans()
  → AgentTraceSpan[]
  → Formatter (OTel / LangSmith / Langfuse / Phoenix / JSONL)
  → External sink
```

Exporters must:

1. Read events from EventStore (may be filtered by visibility).
2. Project to spans.
3. Convert to target format.
4. Batch export.

No exporter is implemented in Phase 1/2. The interface is not yet formalized.

## Relationship with Workbench Trace

Aithru Workbench has its own workflow run trace (deterministic node execution, edge evaluation, state transitions).

Agent trace describes **harness-level intelligent behavior**: model calls, tool requests, approvals, file operations, subagents.

When Workbench calls Agent through `agent.skill` or `agent.task` nodes, the Workbench trace includes a reference to the Agent run `traceId`. The Agent trace remains independently replayable from EventStore.

```txt
Workbench trace:
  agent.skill node
    → references AgentRun traceId = "run_abc123"

Agent trace (independent):
  AgentStreamEvent store for run_abc123
    → projectTraceSpans() → Agent trace timeline
```

## Relationship with Platform Audit

Platform audit (identity, authorization, resource access, token exchange) is separate from Agent trace.

- Audit events are emitted by the Platform SDK and stored in the platform audit log.
- Agent trace does not duplicate platform audit events.
- When a tool call is denied due to missing scopes (`AUTHZ_DENIED`), the Agent emits a `tool.denied` event. The platform independently logs the authz check.
- The `traceId` may be included in audit events for correlation.

## Future Directions

- **Subagent spans**: Each subagent run gets its own span subtree.
- **Sandbox spans**: Execution stdout/stderr as events within a sandbox span.
- **Memory spans**: Read/write operations as instant spans.
- **Context compression**: Completed span subtrees may be summarized and removed from active context while preserving references.
- **Exporter SDK**: Formal interface for writing OTel / LangSmith / Langfuse / Phoenix exporters.
- **Trace UI**: Waterfall view, span detail panel, event-level drill-down, redaction toggle (dev mode).
