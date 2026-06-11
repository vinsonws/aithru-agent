import type { RunId, EventId } from "@aithru/agent-core";
import type { AgentStreamEvent } from "@aithru/agent-stream";

// ── Types ───────────────────────────────────────────────────────────────────

export type AgentTraceSpanKind =
  | "run" | "message" | "model" | "tool" | "approval"
  | "workspace" | "artifact" | "external_run" | "subagent" | "sandbox" | "memory" | "system";

export type AgentTraceSpanStatus = "running" | "completed" | "failed" | "cancelled";

export type AgentTraceSpan = {
  id: string;
  traceId: string;
  runId: RunId;
  parentSpanId?: string;
  kind: AgentTraceSpanKind;
  name: string;
  status: AgentTraceSpanStatus;
  startedAt: string;
  endedAt?: string;
  durationMs?: number;
  eventIds: EventId[];
  refs?: {
    toolCallId?: string;
    approvalId?: string;
    artifactId?: string;
    workspacePath?: string;
    externalKind?: "workflow_capability";
    externalRunId?: string;
    capabilityKey?: string;
    correlationId?: string;
  };
  metrics?: {
    inputTokens?: number;
    outputTokens?: number;
    totalTokens?: number;
    latencyMs?: number;
    costUsd?: number;
  };
  redaction: "none" | "partial" | "full";
  attributes?: Record<string, unknown>;
};

// ── Trace projection ────────────────────────────────────────────────────────

/**
 * Project a sorted list of AgentStreamEvents into AgentTraceSpans.
 *
 * Events must be in sequence order (oldest first) for correct span nesting.
 * The projection maps:
 *   run.created/completed/failed/cancelled → run span
 *   model.started/completed/failed           → model span
 *   tool.proposed/completed/failed/denied    → tool span
 *   approval.requested/resolved              → approval span
 *   workspace.file.created/updated/deleted   → workspace span (instant)
 *   artifact.created                         → artifact span (instant)
 */
export function projectTraceSpans(events: AgentStreamEvent[]): AgentTraceSpan[] {
  const spans: AgentTraceSpan[] = [];
  const openSpans = new Map<string, AgentTraceSpan>();

  const traceId = events.length > 0 ? events[0]!.runId : "empty";

  for (const event of events) {
    switch (event.type) {
      // ── Run lifecycle ──────────────────────────────────────────────────
      case "run.created": {
        spans.push({
          id: `${event.runId}:run`,
          traceId,
          runId: event.runId,
          kind: "run",
          name: "AgentRun",
          status: "running",
          startedAt: event.timestamp,
          eventIds: [event.id],
          redaction: event.redaction,
        });
        openSpans.set(`${event.runId}:run`, spans[spans.length - 1]!);
        break;
      }
      case "run.completed": {
        closeSpan(openSpans, spans, `${event.runId}:run`, "completed", event);
        break;
      }
      case "run.failed": {
        closeSpan(openSpans, spans, `${event.runId}:run`, "failed", event);
        break;
      }
      case "run.cancelled": {
        closeSpan(openSpans, spans, `${event.runId}:run`, "cancelled", event);
        break;
      }

      // ── Model ──────────────────────────────────────────────────────────
      case "model.started": {
        spans.push({
          id: `${event.runId}:model`,
          traceId, runId: event.runId,
          kind: "model", name: "Model Call", status: "running",
          startedAt: event.timestamp, eventIds: [event.id],
          parentSpanId: `${event.runId}:run`,
          redaction: event.redaction,
        });
        openSpans.set(`${event.runId}:model`, spans[spans.length - 1]!);
        break;
      }
      case "model.completed":
        closeSpan(openSpans, spans, `${event.runId}:model`, "completed", event);
        break;
      case "model.failed":
        closeSpan(openSpans, spans, `${event.runId}:model`, "failed", event);
        break;

      // ── Tool ───────────────────────────────────────────────────────────
      case "tool.proposed": {
        const tcId = (event.payload as { toolCallId?: string }).toolCallId ?? "unknown";
        spans.push({
          id: `${event.runId}:tool:${tcId}`,
          traceId, runId: event.runId,
          kind: "tool",
          name: (event.payload as { toolName?: string }).toolName ?? "Tool",
          status: "running",
          startedAt: event.timestamp,
          eventIds: [event.id],
          refs: { toolCallId: tcId },
          redaction: event.redaction,
        });
        openSpans.set(`${event.runId}:tool:${tcId}`, spans[spans.length - 1]!);
        break;
      }
      case "tool.completed":
      case "tool.failed":
      case "tool.denied": {
        const tcIdEnd = (event.payload as { toolCallId?: string }).toolCallId ?? "unknown";
        const st = event.type === "tool.completed" ? "completed" : "failed";
        closeSpan(openSpans, spans, `${event.runId}:tool:${tcIdEnd}`, st, event);
        break;
      }

      // ── Approval ───────────────────────────────────────────────────────
      case "approval.requested": {
        const aId = (event.payload as { approvalId?: string }).approvalId ?? "unknown";
        spans.push({
          id: `${event.runId}:approval:${aId}`,
          traceId, runId: event.runId,
          kind: "approval", name: "Approval", status: "running",
          startedAt: event.timestamp, eventIds: [event.id],
          refs: { approvalId: aId },
          redaction: event.redaction,
        });
        openSpans.set(`${event.runId}:approval:${aId}`, spans[spans.length - 1]!);
        break;
      }
      case "approval.resolved": {
        const aIdRes = (event.payload as { approvalId?: string }).approvalId ?? "unknown";
        closeSpan(openSpans, spans, `${event.runId}:approval:${aIdRes}`, "completed", event);
        break;
      }

      // ── External run references ────────────────────────────────────────
      case "external_run.created": {
        const payload = event.payload as {
          kind?: "workflow_capability";
          capabilityKey?: string;
          capabilityRunId?: string;
          correlationId?: string;
        };
        const externalRunId = payload.capabilityRunId ?? "unknown";
        spans.push({
          id: `${event.runId}:external:${externalRunId}`,
          traceId,
          runId: event.runId,
          kind: "external_run",
          name: payload.capabilityKey ?? "Workflow Capability",
          status: "running",
          startedAt: event.timestamp,
          eventIds: [event.id],
          parentSpanId: `${event.runId}:run`,
          refs: {
            externalKind: payload.kind ?? "workflow_capability",
            externalRunId,
            capabilityKey: payload.capabilityKey,
            correlationId: payload.correlationId,
          },
          redaction: event.redaction,
        });
        openSpans.set(`${event.runId}:external:${externalRunId}`, spans[spans.length - 1]!);
        break;
      }
      case "external_run.completed":
      case "external_run.failed":
      case "external_run.cancelled": {
        const payload = event.payload as { capabilityRunId?: string };
        const externalRunId = payload.capabilityRunId ?? "unknown";
        const status = event.type === "external_run.completed"
          ? "completed"
          : event.type === "external_run.cancelled"
            ? "cancelled"
            : "failed";
        closeSpan(openSpans, spans, `${event.runId}:external:${externalRunId}`, status, event);
        break;
      }

      // ── Workspace (instant spans) ──────────────────────────────────────
      case "workspace.file.created":
      case "workspace.file.updated":
      case "workspace.file.deleted": {
        const wsPath = (event.payload as { path?: string }).path ?? "";
        spans.push({
          id: `${event.runId}:ws:${event.sequence}`,
          traceId, runId: event.runId,
          kind: "workspace", name: event.type, status: "completed",
          startedAt: event.timestamp,
          endedAt: event.timestamp,
          durationMs: 0,
          eventIds: [event.id],
          refs: { workspacePath: wsPath },
          redaction: event.redaction,
        });
        break;
      }

      // ── Artifact (instant spans) ───────────────────────────────────────
      case "artifact.created": {
        const aArtId = (event.payload as { artifactId?: string }).artifactId ?? "unknown";
        spans.push({
          id: `${event.runId}:art:${aArtId}`,
          traceId, runId: event.runId,
          kind: "artifact", name: "Artifact Created", status: "completed",
          startedAt: event.timestamp,
          endedAt: event.timestamp,
          durationMs: 0,
          eventIds: [event.id],
          refs: { artifactId: aArtId },
          redaction: event.redaction,
        });
        break;
      }
    }
  }

  return spans;
}

function closeSpan(
  open: Map<string, AgentTraceSpan>,
  spans: AgentTraceSpan[],
  key: string,
  status: AgentTraceSpanStatus,
  event: AgentStreamEvent,
): void {
  const span = open.get(key);
  if (!span) return;
  span.status = status;
  span.endedAt = event.timestamp;
  if (span.startedAt) {
    span.durationMs = new Date(event.timestamp).getTime() - new Date(span.startedAt).getTime();
  }
  span.eventIds.push(event.id);
  open.delete(key);
}
