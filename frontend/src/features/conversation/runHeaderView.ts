import type { AgentRun, AgentRunStatus, AgentThread } from "@/lib/api";
import {
  humanizeRunStatus,
  formatRunSubline,
  type ProductActionKind,
  type ProductRunStatusCopy,
} from "@/features/chat/runStatusCopy";

export interface RunHeaderActionView {
  kind: ProductActionKind;
  labelKey: string;
  fallback: string;
  disabled?: boolean;
}

export interface RunHeaderView {
  title: string;
  fallbackTitle: string;
  status: ProductRunStatusCopy;
  subline: string;
  modelLabel: string;
  actions: RunHeaderActionView[];
}

export interface RunHeaderInput {
  thread?: AgentThread | null;
  activeRun?: AgentRun | null;
  streamStatus: string;
  streamError?: string | null;
  threadId: string;
  modeLabel?: string;
}

export function buildRunHeaderView(input: RunHeaderInput): RunHeaderView {
  const { thread, activeRun, streamStatus, streamError, modeLabel } = input;

  const title = thread?.title ?? "";
  const runStatus = streamStatus !== "idle" ? streamStatus : (activeRun?.status ?? "idle");
  const status = humanizeRunStatus(runStatus as AgentRunStatus | "idle", {
    error: streamError,
  });

  const subline = formatRunSubline({
    runId: activeRun?.id ?? input.activeRun?.id,
    threadId: input.threadId,
    mode: modeLabel,
  });

  const modelLabel = getModelLabel(activeRun);

  const actions = buildRunHeaderActions({
    status,
    runStatus: runStatus as AgentRunStatus | "idle",
    activeRun,
    streamError,
  });

  return {
    title,
    fallbackTitle: title || "New conversation",
    status,
    subline,
    modelLabel,
    actions,
  };
}

function getModelLabel(activeRun?: AgentRun | null): string {
  const opts = activeRun?.harness_options;
  return opts?.model_profile_key ?? opts?.model ?? "Default model";
}

function buildRunHeaderActions(input: {
  status: ProductRunStatusCopy;
  runStatus: string;
  activeRun?: AgentRun | null;
  streamError?: string | null;
}): RunHeaderActionView[] {
  const { status, runStatus, streamError } = input;

  if (runStatus === "running" || runStatus === "queued") {
    return [
      { kind: "stop", labelKey: "chat:actions.stop", fallback: "Stop" },
    ];
  }

  if (runStatus === "waiting_input") {
    return [
      { kind: "reply", labelKey: "chat:actions.reply", fallback: "Reply" },
    ];
  }

  if (runStatus === "waiting_approval") {
    return [
      { kind: "reviewApproval", labelKey: "chat:actions.reviewApproval", fallback: "Review approval" },
    ];
  }

  if (runStatus === "failed") {
    const actions: RunHeaderActionView[] = [];
    if (status.failureCategory === "modelConfiguration") {
      actions.push({ kind: "openModelSettings", labelKey: "chat:actions.openModelSettings", fallback: "Open model settings" });
    } else {
      actions.push({ kind: "retry", labelKey: "chat:actions.retry", fallback: "Retry" });
    }
    if (streamError) {
      actions.push({ kind: "viewTrace", labelKey: "chat:actions.viewTrace", fallback: "View trace" });
    }
    return actions;
  }

  if (runStatus === "completed") {
    return [
      { kind: "newFollowUp", labelKey: "chat:actions.newFollowUp", fallback: "New follow-up" },
      { kind: "retry", labelKey: "chat:actions.retry", fallback: "Retry" },
    ];
  }

  if (runStatus === "cancelled") {
    return [
      { kind: "retry", labelKey: "chat:actions.retry", fallback: "Retry" },
    ];
  }

  return [];
}
