import type { AgentStreamEvent } from "../contracts/types.js";
import type { AgentTraceSpan } from "./spans.js";

interface SpanBuilder {
  span: AgentTraceSpan;
  activeChildren: Map<string, SpanBuilder>;
}

function createSpan(
  runId: string,
  id: string,
  kind: string,
  name: string,
  timestamp: string,
  parentId?: string,
): AgentTraceSpan {
  return {
    id,
    run_id: runId,
    parent_id: parentId,
    kind,
    name,
    started_at: timestamp,
    status: "ok",
    children: [],
  };
}

export function projectTraceSpans(events: AgentStreamEvent[]): AgentTraceSpan[] {
  const runSpans: Map<string, SpanBuilder> = new Map();
  const toolCallSpans: Map<string, SpanBuilder> = new Map();
  const roots: AgentTraceSpan[] = [];

  // Sort events by sequence for deterministic ordering
  const sorted = [...events].sort((a, b) => a.sequence - b.sequence);

  for (const event of sorted) {
    const payload = (event.payload as Record<string, any>) || {};

    switch (event.type) {
      case "run.started": {
        const span = createSpan(event.run_id, event.id, "run", "Agent Run", event.timestamp);
        runSpans.set(event.run_id, { span, activeChildren: new Map() });
        roots.push(span);
        break;
      }

      case "message.created": {
        const runBuilder = runSpans.get(event.run_id);
        if (!runBuilder) continue;
        const span = createSpan(
          event.run_id, event.id, "message",
          `Message ${payload.message_id || ""}`,
          event.timestamp, runBuilder.span.id,
        );
        runBuilder.activeChildren.set(event.id, { span, activeChildren: new Map() });
        runBuilder.span.children.push(span);
        break;
      }

      case "message.completed": {
        const runBuilder = runSpans.get(event.run_id);
        const child = runBuilder?.activeChildren.get(event.id);
        if (child) {
          child.span.completed_at = event.timestamp;
          child.span.metadata = { ...child.span.metadata, content: payload.content };
        }
        break;
      }

      case "tool.proposed": {
        const runBuilder = runSpans.get(event.run_id);
        if (!runBuilder) continue;
        const toolCallId = payload.tool_call_id;
        const span = createSpan(
          event.run_id, toolCallId || event.id, "tool",
          payload.name || "tool_call",
          event.timestamp, runBuilder.span.id,
        );
        toolCallSpans.set(toolCallId, { span, activeChildren: new Map() });
        runBuilder.span.children.push(span);
        break;
      }

      case "tool.completed": {
        const toolSpan = toolCallSpans.get(payload.tool_call_id);
        if (toolSpan) {
          toolSpan.span.completed_at = event.timestamp;
          toolSpan.span.status = "ok";
          toolSpan.span.metadata = { output: payload.output };
        }
        break;
      }

      case "tool.failed": {
        const toolSpan = toolCallSpans.get(payload.tool_call_id);
        if (toolSpan) {
          toolSpan.span.completed_at = event.timestamp;
          toolSpan.span.status = "error";
          toolSpan.span.metadata = { error: payload.error };
        }
        break;
      }

      case "tool.denied":
      case "tool.scope_denied":
      case "tool.skill_denied": {
        const toolSpan = toolCallSpans.get(payload.tool_call_id);
        if (toolSpan) {
          toolSpan.span.completed_at = event.timestamp;
          toolSpan.span.status = "cancelled";
          toolSpan.span.metadata = { reason: payload.reason };
        }
        break;
      }

      case "run.completed": {
        const runBuilder = runSpans.get(event.run_id);
        if (runBuilder) {
          runBuilder.span.completed_at = event.timestamp;
          runBuilder.span.status = "ok";
        }
        break;
      }

      case "run.failed": {
        const runBuilder = runSpans.get(event.run_id);
        if (runBuilder) {
          runBuilder.span.completed_at = event.timestamp;
          runBuilder.span.status = "error";
          runBuilder.span.metadata = { error: payload.error };
        }
        break;
      }

      case "run.cancelled": {
        const runBuilder = runSpans.get(event.run_id);
        if (runBuilder) {
          runBuilder.span.completed_at = event.timestamp;
          runBuilder.span.status = "cancelled";
        }
        break;
      }
    }
  }

  return roots;
}
