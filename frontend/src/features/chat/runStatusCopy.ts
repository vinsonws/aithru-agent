import type { AgentRunStatus } from "@/lib/api";

export type ProductStatusTone =
  | "muted"
  | "queued"
  | "live"
  | "waiting"
  | "success"
  | "danger"
  | "cancelled";

export type ProductActionKind =
  | "stop"
  | "reply"
  | "reviewApproval"
  | "retry"
  | "viewTrace"
  | "openModelSettings"
  | "newFollowUp";

export type ProductFailureCategory =
  | "modelConfiguration"
  | "approval"
  | "capability"
  | "unknown";

export interface ProductRunStatusCopy {
  status: AgentRunStatus | "idle";
  labelKey: string;
  fallback: string;
  tone: ProductStatusTone;
  primaryAction?: ProductActionKind;
  failureCategory?: ProductFailureCategory;
}

const STATUS_MAP: Record<string, ProductRunStatusCopy> = {
  idle: { status: "idle", labelKey: "chat:status.notStarted", fallback: "Not started", tone: "muted" },
  queued: { status: "queued", labelKey: "chat:status.queued", fallback: "Queued", tone: "queued" },
  running: { status: "running", labelKey: "chat:status.running", fallback: "Running", tone: "live", primaryAction: "stop" },
  waiting_input: { status: "waiting_input", labelKey: "chat:status.awaitingReply", fallback: "Awaiting reply", tone: "waiting", primaryAction: "reply" },
  waiting_approval: { status: "waiting_approval", labelKey: "chat:status.approvalNeeded", fallback: "Approval needed", tone: "waiting", primaryAction: "reviewApproval" },
  waiting_subagent: { status: "waiting_subagent", labelKey: "chat:status.awaitingReply", fallback: "Awaiting reply", tone: "waiting", primaryAction: "reply" },
  waiting_external_run: { status: "waiting_external_run", labelKey: "chat:status.waitingExternalRun", fallback: "Waiting on external run", tone: "waiting" },
  completed: { status: "completed", labelKey: "chat:status.completed", fallback: "Completed", tone: "success", primaryAction: "newFollowUp" },
  failed: { status: "failed", labelKey: "chat:status.failed", fallback: "Failed", tone: "danger", primaryAction: "retry" },
  cancelled: { status: "cancelled", labelKey: "chat:status.cancelled", fallback: "Cancelled", tone: "cancelled", primaryAction: "retry" },
};

export function humanizeRunStatus(
  status?: string | null,
  options?: { error?: string | null },
): ProductRunStatusCopy {
  const key = status ?? "idle";
  const result = STATUS_MAP[key] ?? STATUS_MAP.idle;
  if (result.status === "failed" && options?.error) {
    const failureCategory = classifyRunFailure(options.error);
    return {
      ...result,
      failureCategory,
      primaryAction: failureCategory === "modelConfiguration" ? "openModelSettings" : "retry",
    };
  }
  return result;
}

export function formatShortRunId(id?: string | null): string {
  if (!id) return "";
  const parts = id.split("_");
  if (parts.length >= 2 && parts[1].length > 4) {
    return `${parts[0]}_${parts[1].slice(0, 4)}`;
  }
  return id;
}

export function formatRunSubline(input: {
  runId?: string | null;
  threadId?: string | null;
  mode?: string | null;
}): string {
  const parts: string[] = [];
  if (input.runId) parts.push(formatShortRunId(input.runId));
  if (input.threadId) parts.push(formatShortRunId(input.threadId));
  if (input.mode) parts.push(input.mode);
  return parts.join(" · ");
}

export function classifyRunFailure(error?: string | null): ProductFailureCategory {
  if (!error) return "unknown";
  const lower = error.toLowerCase();
  if (
    lower.includes("api key") ||
    lower.includes("metadata cannot include secret") ||
    lower.includes("base_url") ||
    lower.includes("provider") ||
    lower.includes("model configuration")
  )
    return "modelConfiguration";
  if (lower.includes("approval") || lower.includes("denied") || lower.includes("permission"))
    return "approval";
  if (lower.includes("tool") || lower.includes("capability") || lower.includes("workspace") || lower.includes("sandbox"))
    return "capability";
  return "unknown";
}

export function isTerminalRunStatus(status?: AgentRunStatus | "idle" | null): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}

export function isActiveRunStatus(status?: AgentRunStatus | "idle" | null): boolean {
  return (
    status === "running" ||
    status === "queued" ||
    status === "waiting_input" ||
    status === "waiting_approval" ||
    status === "waiting_subagent" ||
    status === "waiting_external_run"
  );
}
