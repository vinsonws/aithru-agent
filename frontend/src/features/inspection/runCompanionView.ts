import { buildRunCompanionBadges } from "@/features/chat/runActivity";
import type { RunStreamState } from "@/features/chat/useRunStream";

export type RunCompanionStatusTone =
  | "muted"
  | "live"
  | "waiting"
 | "success"
  | "danger"
  | "cancelled";

export interface RunCompanionRailView {
  status: string | null;
  statusTone: RunCompanionStatusTone;
  progressLabel: string | null;
  attentionCount: number;
  hasAttention: boolean;
}

export function buildRunCompanionRailView(input: {
  runStatus?: string | null;
  todoProgress?: { done: number; total: number } | null;
  streamState: RunStreamState;
}): RunCompanionRailView {
  const badges = buildRunCompanionBadges(input.streamState);
  const actionAttention = badges.activity + badges.approvals + badges.trace;
  const outputAttention = input.runStatus === "completed" ? badges.files : 0;
  const attentionCount = actionAttention + outputAttention;
  const total = input.todoProgress?.total ?? 0;

  return {
    status: input.runStatus ?? null,
    statusTone: statusTone(input.runStatus),
    progressLabel:
      total > 0 && input.todoProgress
        ? `${input.todoProgress.done}/${input.todoProgress.total}`
        : null,
    attentionCount,
    hasAttention: attentionCount > 0,
  };
}

function statusTone(status?: string | null): RunCompanionStatusTone {
  if (status === "running" || status === "queued") return "live";
  if (
    status === "waiting_input" ||
    status === "waiting_approval" ||
    status === "waiting_external" ||
    status === "paused"
  ) {
    return "waiting";
  }
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "cancelled") return "cancelled";
  return "muted";
}
