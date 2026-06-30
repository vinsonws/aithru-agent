import type { AgentRun, AgentRunStatus, AgentThread } from "@/lib/api";
import {
  humanizeRunStatus,
  formatRunSubline,
  type ProductActionKind,
  type ProductRunStatusCopy,
} from "@/features/chat/runStatusCopy";
import { getPermissionPolicy, inferPermissionPolicyFromScopes } from "@/features/chat/composerState";

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
  permissionLabel?: string;
  permissionLabelKey?: string;
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
  const permission = activeRun
    ? getPermissionPolicy(inferPermissionPolicyFromScopes(activeRun.scopes))
    : null;

  return {
    title,
    fallbackTitle: title || "New conversation",
    status,
    subline,
    modelLabel,
    permissionLabel: permission?.fallback,
    permissionLabelKey: permission?.labelKey,
    actions: [],
  };
}

function getModelLabel(activeRun?: AgentRun | null): string {
  const opts = activeRun?.harness_options;
  return opts?.model_profile_key ?? opts?.model ?? "";
}

export type RunMode = "flash" | "thinking" | "pro" | "ultra";

export function getRunMode(activeRun?: AgentRun | null): RunMode {
  const mode = activeRun?.harness_options?.mode;
  if (mode === "flash" || mode === "thinking" || mode === "pro" || mode === "ultra") {
    return mode;
  }
  const instructions = activeRun?.harness_options?.instructions ?? "";
  const match = /\[Aithru mode: (auto|plan|chat)\]/i.exec(instructions);
  const legacyMode = match?.[1]?.toLowerCase();
  if (legacyMode === "plan") return "pro";
  if (legacyMode === "chat") return "flash";
  return "thinking";
}
