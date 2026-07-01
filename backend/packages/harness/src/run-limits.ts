import type { AgentRun, AgentStreamEvent } from "@aithru-agent/contracts";
import { validateRunStatusTransition } from "@aithru-agent/contracts";
import type { AgentStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";

export type RunLimitKind = "model_requests" | "tool_executions" | "tokens" | "repeat_tool_call";

export interface AgentRunLimits {
  maxModelRequests: number;
  maxToolExecutions: number;
  maxInputTokens?: number;
  maxOutputTokens?: number;
  maxTotalTokens?: number;
}

export const LIMIT_CONTINUATION_TOOL = "agent.limit.continue";
export const LIMIT_CONTINUATION_INCREMENT = {
  maxModelRequests: 25,
  maxToolExecutions: 50,
} as const;

const DEFAULT_LIMITS = { maxModelRequests: 50, maxToolExecutions: 100 };
const ULTRA_LIMITS = { maxModelRequests: 100, maxToolExecutions: 200 };
const WARN_THRESHOLD = 0.8;

function modeOf(run: AgentRun): string | null {
  const opts = run.harness_options as Record<string, unknown> | null | undefined;
  if (!opts || typeof opts !== "object") return null;
  const mode = opts.mode;
  return typeof mode === "string" ? mode : null;
}

function defaultLimitsForMode(mode: string | null): { maxModelRequests: number; maxToolExecutions: number } {
  if (mode === "ultra") return { ...ULTRA_LIMITS };
  return { ...DEFAULT_LIMITS };
}

export function resolveRunLimits(run: AgentRun, events: AgentStreamEvent[]): AgentRunLimits {
  const defaults = defaultLimitsForMode(modeOf(run));
  const configured = configuredLimits(run);
  let maxModelRequests = configured.maxModelRequests ?? defaults.maxModelRequests;
  let maxToolExecutions = configured.maxToolExecutions ?? defaults.maxToolExecutions;
  for (const event of events) {
    if (event.type !== EVENT_TYPES.APPROVAL_RESOLVED) continue;
    const payload = event.payload as Record<string, unknown>;
    if (payload.name !== LIMIT_CONTINUATION_TOOL) continue;
    if (payload.decision !== "approved") continue;
    maxModelRequests += LIMIT_CONTINUATION_INCREMENT.maxModelRequests;
    maxToolExecutions += LIMIT_CONTINUATION_INCREMENT.maxToolExecutions;
  }
  return { maxModelRequests, maxToolExecutions };
}

function configuredLimits(run: AgentRun): Partial<Pick<AgentRunLimits, "maxModelRequests" | "maxToolExecutions">> {
  const opts = run.harness_options as Record<string, unknown> | null | undefined;
  if (!opts || typeof opts !== "object") return {};
  return {
    maxModelRequests: positiveInteger(opts.max_model_requests),
    maxToolExecutions: positiveInteger(opts.max_tool_executions),
  };
}

function positiveInteger(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.floor(value)
    : undefined;
}

export function countModelRequests(events: AgentStreamEvent[]): number {
  return events.filter((e) => e.type === EVENT_TYPES.CONTEXT_PACKET_BUILT).length;
}

export function countToolExecutions(events: AgentStreamEvent[]): number {
  return events.filter((e) => e.type === EVENT_TYPES.TOOL_STARTED).length;
}

export function countTokenUsage(events: AgentStreamEvent[]): { input_tokens: number; output_tokens: number; total_tokens: number } {
  let input = 0;
  let output = 0;
  let total = 0;
  for (const event of events) {
    if (event.type !== EVENT_TYPES.MODEL_USAGE) continue;
    const payload = event.payload as Record<string, unknown>;
    input += numberValue(payload.input_tokens) ?? 0;
    output += numberValue(payload.output_tokens) ?? 0;
    total += numberValue(payload.total_tokens) ?? 0;
  }
  return { input_tokens: input, output_tokens: output, total_tokens: total };
}

export function shouldWarnAtLimit(
  kind: RunLimitKind,
  current: number,
  limit: number,
  events: AgentStreamEvent[],
): boolean {
  if (limit <= 0) return false;
  if (current < limit * WARN_THRESHOLD) return false;
  return !events.some(
    (e) => e.type === EVENT_TYPES.LIMIT_WARNING
      && (e.payload as Record<string, unknown>)?.kind === kind,
  );
}

export function writeLimitWarning(deps: {
  eventWriter: AgentEventWriter;
  run: AgentRun;
  kind: RunLimitKind;
  current: number;
  limit: number;
  message: string;
}): void {
  deps.eventWriter.write(
    deps.run.id,
    deps.run.thread_id ?? null,
    EVENT_TYPES.LIMIT_WARNING,
    {
      kind: deps.kind,
      current: deps.current,
      limit: deps.limit,
      message: deps.message,
    },
  );
}

export function pauseForLimitContinuation(deps: {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  run: AgentRun;
  kind: RunLimitKind;
  current: number;
  limit: number;
  message: string;
}): AgentRun {
  const { store, eventWriter, run, kind, current, limit, message } = deps;
  const existingApprovals = store.listApprovals({ run_id: run.id });
  const seq = existingApprovals.length + 1;
  const toolCallId = `limit:${kind}:${seq}`;
  const approvalId = `aprv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;

  store.createApproval({
    id: approvalId,
    run_id: run.id,
    tool_call_id: toolCallId,
    tool_name: LIMIT_CONTINUATION_TOOL,
    status: "pending",
    created_at: nowIso(),
  });

  eventWriter.write(
    run.id,
    run.thread_id ?? null,
    EVENT_TYPES.APPROVAL_REQUESTED,
    {
      approval_id: approvalId,
      tool_call_id: toolCallId,
      name: LIMIT_CONTINUATION_TOOL,
      kind,
      current,
      limit,
      message,
    },
  );

  validateRunStatusTransition(run.status as string, "waiting_approval");
  const updated = store.updateRun(run.id, {
    status: "waiting_approval",
    current_approval_id: approvalId,
  });

  eventWriter.write(
    run.id,
    run.thread_id ?? null,
    EVENT_TYPES.RUN_PAUSED,
    {
      reason: "limit_continuation_required",
      approval_id: approvalId,
      kind,
      current,
      limit,
    },
  );

  return updated;
}

export function isLimitContinuationApproval(value: { tool_name?: string }): boolean {
  return value.tool_name === LIMIT_CONTINUATION_TOOL;
}

export function limitKindFromToolCallId(toolCallId: string): RunLimitKind | null {
  const parts = toolCallId.split(":");
  if (parts.length < 3 || parts[0] !== "limit") return null;
  return parts[1] as RunLimitKind;
}

export type RepeatState = "ok" | "warn" | "pause";

export function repeatToolCallState(
  events: AgentStreamEvent[],
  name: string,
  input: Record<string, unknown>,
): RepeatState {
  const fingerprint = toolCallFingerprint(name, input);
  let count = 0;
  for (const event of events) {
    if (event.type !== EVENT_TYPES.TOOL_PROPOSED) continue;
    const payload = event.payload as Record<string, unknown>;
    const eventName = payload.name;
    const eventInput = payload.input;
    if (typeof eventName !== "string") continue;
    if (toolCallFingerprint(eventName, eventInput as Record<string, unknown>) === fingerprint) {
      count += 1;
    }
  }
  if (count >= 4) return "pause";
  if (count >= 2) return "warn";
  return "ok";
}

function toolCallFingerprint(name: string, input: Record<string, unknown>): string {
  return `${name}:${canonicalJson(input)}`;
}

function canonicalJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value !== "object" || Array.isArray(value)) {
    return JSON.stringify(value);
  }
  const keys = Object.keys(value as Record<string, unknown>).sort();
  const parts = keys.map(
    (k) => `${JSON.stringify(k)}:${canonicalJson((value as Record<string, unknown>)[k])}`,
  );
  return `{${parts.join(",")}}`;
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number") return value;
  return undefined;
}

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}
