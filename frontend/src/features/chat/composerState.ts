import type { AgentRunHarnessOptions } from "@/lib/api";

export type ComposerMode = "auto" | "plan" | "chat";
export type ComposerPermissionPolicyId = "ask" | "auto_safe" | "read_only";
export type ComposerReasoningLevel = "quick" | "thinking" | "pro" | "ultra";
export type ComposerModelReasoningEffort = "none" | "low" | "medium" | "high";

export interface ComposerPermissionPolicy {
  id: ComposerPermissionPolicyId;
  labelKey: string;
  fallback: string;
  descriptionKey: string;
  fallbackDescription: string;
  scopes: string[];
}

export interface ComposerReasoningOption {
  id: ComposerReasoningLevel;
  labelKey: string;
  fallback: string;
  descriptionKey: string;
  fallbackDescription: string;
}

export const REASONING_LEVELS: ComposerReasoningOption[] = [
  {
    id: "quick",
    labelKey: "chat:reasoning.quick",
    fallback: "Quick",
    descriptionKey: "chat:reasoning.quickDescription",
    fallbackDescription: "Fast responses for direct tasks.",
  },
  {
    id: "thinking",
    labelKey: "chat:reasoning.thinking",
    fallback: "Thinking",
    descriptionKey: "chat:reasoning.thinkingDescription",
    fallbackDescription: "Balance speed and accuracy before acting.",
  },
  {
    id: "pro",
    labelKey: "chat:reasoning.pro",
    fallback: "Pro",
    descriptionKey: "chat:reasoning.proDescription",
    fallbackDescription: "Plan before execution for more precise results.",
  },
  {
    id: "ultra",
    labelKey: "chat:reasoning.ultra",
    fallback: "Ultra",
    descriptionKey: "chat:reasoning.ultraDescription",
    fallbackDescription: "Use the most careful planning for complex work.",
  },
];

export const MODE_INSTRUCTIONS: Record<ComposerMode, string | null> = {
  auto: null,
  plan: "[Aithru mode: plan]\nWork in planning mode. Produce a clear implementation plan before making changes.",
  chat: "[Aithru mode: chat]\nWork in chat mode. Answer directly and avoid taking tool-driven actions unless the user asks for execution.",
};

export const PERMISSION_POLICIES: ComposerPermissionPolicy[] = [
  {
    id: "ask",
    labelKey: "chat:permission.ask",
    fallback: "Ask",
    descriptionKey: "chat:permission.askDescription",
    fallbackDescription: "Allow common task tools while backend approval policy gates risky actions.",
    scopes: [
      "agent.workspace.read",
      "agent.workspace.write",
      "agent.todo.write",
      "agent.research.write",
      "agent.input.write",
      "agent.memory.read",
    ],
  },
  {
    id: "auto_safe",
    labelKey: "chat:permission.autoSafe",
    fallback: "Full access",
    descriptionKey: "chat:permission.autoSafeDescription",
    fallbackDescription: "Trusted local mode that requests broad capability access.",
    scopes: ["*"],
  },
  {
    id: "read_only",
    labelKey: "chat:permission.readOnly",
    fallback: "Read-only",
    descriptionKey: "chat:permission.readOnlyDescription",
    fallbackDescription: "Inspect workspace and memory without write scopes.",
    scopes: ["agent.workspace.read", "agent.memory.read"],
  },
];

const PERMISSION_POLICY_IDS = new Set(PERMISSION_POLICIES.map((policy) => policy.id));
const REASONING_LEVEL_IDS = new Set(REASONING_LEVELS.map((level) => level.id));
const REASONING_EFFORT_BY_LEVEL: Record<
  ComposerReasoningLevel,
  ComposerModelReasoningEffort
> = {
  quick: "none",
  thinking: "low",
  pro: "medium",
  ultra: "high",
};

export function normalizeComposerMode(value: string | null | undefined): ComposerMode {
  return value === "plan" || value === "chat" || value === "auto" ? value : "auto";
}

export function normalizeReasoningLevel(
  value: string | null | undefined,
): ComposerReasoningLevel {
  return REASONING_LEVEL_IDS.has(value as ComposerReasoningLevel)
    ? (value as ComposerReasoningLevel)
    : "pro";
}

export function composerModeForReasoningLevel(
  value: string | null | undefined,
): ComposerMode {
  const level = normalizeReasoningLevel(value);
  if (level === "quick") return "chat";
  if (level === "thinking") return "auto";
  return "plan";
}

export function reasoningLevelForComposerMode(
  value: string | null | undefined,
): ComposerReasoningLevel {
  const mode = normalizeComposerMode(value);
  if (mode === "chat") return "quick";
  if (mode === "auto") return "thinking";
  return "pro";
}

export function reasoningEffortForReasoningLevel(
  value: string | null | undefined,
): ComposerModelReasoningEffort {
  return REASONING_EFFORT_BY_LEVEL[normalizeReasoningLevel(value)];
}

export function normalizePermissionPolicyId(
  value: string | null | undefined,
): ComposerPermissionPolicyId {
  return PERMISSION_POLICY_IDS.has(value as ComposerPermissionPolicyId)
    ? (value as ComposerPermissionPolicyId)
    : "ask";
}

export function getPermissionPolicy(
  value: string | null | undefined,
): ComposerPermissionPolicy {
  const id = normalizePermissionPolicyId(value);
  return PERMISSION_POLICIES.find((policy) => policy.id === id) ?? PERMISSION_POLICIES[0];
}

export function buildComposerHarnessOptions(
  profileKey: string | null,
  mode: string,
  reasoningLevel: string | null | undefined,
): AgentRunHarnessOptions | undefined {
  const normalizedMode = normalizeComposerMode(mode);
  const reasoningEffort = reasoningEffortForReasoningLevel(reasoningLevel);
  const harnessOptions: AgentRunHarnessOptions & {
    model_reasoning_effort?: ComposerModelReasoningEffort;
  } = {
    model_capabilities: {
      vision: false,
      thinking: reasoningEffort !== "none",
    },
    model_reasoning_effort: reasoningEffort,
  };
  if (profileKey) {
    harnessOptions.model_profile_key = profileKey;
  }
  const instructions = MODE_INSTRUCTIONS[normalizedMode];
  if (instructions) {
    harnessOptions.instructions = instructions;
  }
  return Object.keys(harnessOptions).length > 0 ? harnessOptions : undefined;
}

export function buildComposerScopes(policyId: string | null | undefined): string[] {
  return [...getPermissionPolicy(policyId).scopes];
}

export function inferPermissionPolicyFromScopes(
  scopes: string[] | null | undefined,
): ComposerPermissionPolicyId {
  const normalized = new Set(scopes ?? []);
  if (normalized.has("*")) return "auto_safe";
  const hasWrite = [...normalized].some((scope) => scope.endsWith(".write"));
  if (hasWrite) return "ask";
  if (normalized.has("agent.workspace.read") || normalized.has("agent.memory.read")) return "read_only";
  return "ask";
}

export function permissionPolicyLabelKey(policyId: string | null | undefined): string {
  return getPermissionPolicy(policyId).labelKey;
}

export interface ComposerSummaryInput {
  mode: string | null | undefined;
  profileKey: string | null | undefined;
  profileName: string | null | undefined;
  skillId: string | null | undefined;
  skillName: string | null | undefined;
  permissionPolicy: string | null | undefined;
}

export interface ComposerSummaryParts {
  modeLabelKey: string;
  modeFallback: string;
  modelLabel: string;
  skillLabel: string | null;
  permissionLabelKey: string;
  permissionFallback: string;
}

const MODE_LABELS: Record<ComposerMode, { labelKey: string; fallback: string }> = {
  auto: { labelKey: "chat:modeAuto", fallback: "Auto" },
  plan: { labelKey: "chat:modePlan", fallback: "Plan" },
  chat: { labelKey: "chat:modeChat", fallback: "Chat" },
};

export function buildComposerSummaryParts(input: ComposerSummaryInput): ComposerSummaryParts {
  const mode = normalizeComposerMode(input.mode);
  const permission = getPermissionPolicy(input.permissionPolicy);
  const profileKey = input.profileKey ?? "";
  const skillId = input.skillId ?? "__none__";

  return {
    modeLabelKey: MODE_LABELS[mode].labelKey,
    modeFallback: MODE_LABELS[mode].fallback,
    modelLabel:
      profileKey
        ? input.profileName?.trim() || profileKey
        : "No model",
    skillLabel:
      skillId === "__none__"
        ? null
        : input.skillName?.trim() || skillId,
    permissionLabelKey: permission.labelKey,
    permissionFallback: permission.fallback,
  };
}

export function buildComposerSummaryLabel(input: {
  modeLabel: string;
  modelLabel: string;
  skillLabel: string | null;
  permissionLabel: string;
}): string {
  return [
    input.modeLabel,
    input.modelLabel,
    input.skillLabel,
    input.permissionLabel,
  ]
    .filter((part): part is string => Boolean(part))
    .join(" / ");
}
