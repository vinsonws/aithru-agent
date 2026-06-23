import type { AgentRun } from "@/lib/api";
import type { RunStreamState } from "@/features/chat/useRunStream";
import { buildRunActivity } from "@/features/chat/runActivity";
import { getPermissionPolicy, inferPermissionPolicyFromScopes } from "@/features/chat/composerState";

export interface RunTaskLoopView {
  goal: string;
  modeLabel: string;
  modelLabel: string;
  permission: {
    id: string;
    labelKey: string;
    fallback: string;
  };
  currentTitle: string;
  currentDetail?: string;
  progress: { done: number; total: number };
}

export function buildRunTaskLoopView(input: {
  activeRun?: AgentRun | null;
  streamState?: RunStreamState | null;
  modeLabel: string;
  defaultModelLabel?: string;
}): RunTaskLoopView | null {
  const { activeRun } = input;
  if (!activeRun) return null;

  const permissionId = inferPermissionPolicyFromScopes(activeRun.scopes);
  const permission = getPermissionPolicy(permissionId);
  const activity = input.streamState ? buildRunActivity(input.streamState) : null;

  return {
    goal: activeRun.goal,
    modeLabel: input.modeLabel,
    modelLabel:
      activeRun.harness_options?.model_profile_key ??
      activeRun.harness_options?.model ??
      input.defaultModelLabel ??
      "Default model",
    permission: {
      id: permission.id,
      labelKey: permission.labelKey,
      fallback: permission.fallback,
    },
    currentTitle: activity?.narrative.title ?? "Waiting for activity",
    currentDetail: activity?.narrative.detail,
    progress: activity?.progress ?? { done: 0, total: 0 },
  };
}
