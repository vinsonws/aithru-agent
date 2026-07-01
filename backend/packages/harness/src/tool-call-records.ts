import type { AgentModelToolResult } from "@aithru-agent/model";
import type { AgentApproval, AgentStore } from "@aithru-agent/persistence";
import { EVENT_TYPES } from "@aithru-agent/stream";

export const TOOL_CALL_RECORD_KIND = "tool_call_record";

export type ToolCallRecordStatus =
  | "proposed"
  | "waiting_approval"
  | "running"
  | "completed"
  | "failed"
  | "denied";

export interface ToolCallRecord {
  id: string;
  run_id: string;
  tool_name: string;
  input: Record<string, unknown>;
  status: ToolCallRecordStatus;
  approval_id?: string | null;
  reasoning_content?: string;
  output?: unknown;
  error?: AgentModelToolResult["error"] | null;
  created_at: string;
  updated_at: string;
}

export function createToolCallRecord(store: AgentStore, record: ToolCallRecord): ToolCallRecord {
  store.upsertDocument(TOOL_CALL_RECORD_KIND, record.id, record);
  return record;
}

export function getToolCallRecord(store: AgentStore, id: string): ToolCallRecord | null {
  return normalizeToolCallRecord(store.getDocument(TOOL_CALL_RECORD_KIND, id)?.payload);
}

export function updateToolCallRecord(
  store: AgentStore,
  id: string,
  patch: Partial<Omit<ToolCallRecord, "id" | "created_at">>,
): ToolCallRecord {
  const existing = getToolCallRecord(store, id);
  if (!existing) throw new Error(`Tool call record not found: ${id}`);
  return createToolCallRecord(store, {
    ...existing,
    ...patch,
    updated_at: nowIso(),
  });
}

export function ensureToolCallRecordForApproval(
  store: AgentStore,
  approval: AgentApproval,
): ToolCallRecord | null {
  const existing = getToolCallRecord(store, approval.tool_call_id);
  if (existing && existing.run_id === approval.run_id && existing.tool_name === approval.tool_name) {
    return existing;
  }

  const proposed = [...store.listEvents(approval.run_id)].reverse().find((event) => {
    const payload = isRecord(event.payload) ? event.payload : {};
    return event.type === EVENT_TYPES.TOOL_PROPOSED && payload.tool_call_id === approval.tool_call_id;
  });
  const payload = isRecord(proposed?.payload) ? proposed.payload : {};
  if (payload.name !== approval.tool_name || !isRecord(payload.input)) return null;

  return createToolCallRecord(store, {
    id: approval.tool_call_id,
    run_id: approval.run_id,
    tool_name: approval.tool_name,
    input: payload.input,
    status: "waiting_approval",
    approval_id: approval.id,
    created_at: proposed?.timestamp ?? nowIso(),
    updated_at: nowIso(),
  });
}

export function toolResultFromRecord(record: ToolCallRecord): AgentModelToolResult | null {
  if (record.status === "completed") {
    return {
      id: record.id,
      name: record.tool_name,
      input: record.input,
      output: record.output ?? null,
      ...(typeof record.reasoning_content === "string" ? { reasoning_content: record.reasoning_content } : {}),
    };
  }
  if (record.status === "failed" || record.status === "denied") {
    return {
      id: record.id,
      name: record.tool_name,
      input: record.input,
      output: null,
      ...(typeof record.reasoning_content === "string" ? { reasoning_content: record.reasoning_content } : {}),
      error: record.error ?? {
        code: record.status === "denied" ? "TOOL_DENIED" : "TOOL_FAILED",
        message: record.status === "denied" ? "Tool call denied by user approval decision" : "Tool call failed",
        retryable: false,
      },
    };
  }
  return null;
}

function normalizeToolCallRecord(value: unknown): ToolCallRecord | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.id !== "string" ||
    typeof value.run_id !== "string" ||
    typeof value.tool_name !== "string" ||
    !isRecord(value.input) ||
    !isToolCallRecordStatus(value.status) ||
    typeof value.created_at !== "string" ||
    typeof value.updated_at !== "string"
  ) {
    return null;
  }
  return value as unknown as ToolCallRecord;
}

function isToolCallRecordStatus(value: unknown): value is ToolCallRecordStatus {
  return (
    value === "proposed" ||
    value === "waiting_approval" ||
    value === "running" ||
    value === "completed" ||
    value === "failed" ||
    value === "denied"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}
