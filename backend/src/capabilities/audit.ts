import type { AgentStreamEvent } from "@aithru-agent/contracts";

export interface AgentCapabilityAuditEntry {
  event_id: string;
  sequence: number;
  type: string;
  tool_call_id: string | null;
  tool_name: string | null;
  decision: string;
  reason?: string;
  visibility: string;
  redaction: string;
}

const DECISION_BY_EVENT: Record<string, string> = {
  "tool.proposed": "proposed",
  "tool.started": "started",
  "tool.completed": "completed",
  "tool.failed": "failed",
  "tool.denied": "denied",
  "tool.scope_denied": "scope_denied",
  "tool.skill_denied": "skill_denied",
  "tool.unknown": "unknown",
};

export function projectCapabilityAudit(
  events: AgentStreamEvent[],
): AgentCapabilityAuditEntry[] {
  return events
    .filter((event) => event.type.startsWith("tool."))
    .map((event) => {
      const payload = event.payload as Record<string, unknown>;
      return {
        event_id: event.id,
        sequence: event.sequence,
        type: event.type,
        tool_call_id:
          payload?.tool_call_id == null ? null : String(payload.tool_call_id),
        tool_name: payload?.name == null ? null : String(payload.name),
        decision: DECISION_BY_EVENT[event.type] ?? "observed",
        reason: payload?.reason == null ? undefined : String(payload.reason),
        visibility: event.visibility,
        redaction: event.redaction,
      };
    });
}
