import type { AgentRunHarnessOptions } from "@/lib/api";

export type ComposerMode = "flash" | "thinking" | "pro" | "ultra";
export type ComposerPermissionPolicyId = "ask" | "auto_safe" | "read_only";
export type ComposerReasoningLevel = ComposerMode;
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

export interface ComposerModelProfile {
  key: string;
  enabled?: boolean;
  model?: string | null;
}

export interface ComposerModelProvider {
  key: string;
  name?: string | null;
  enabled?: boolean;
  models?: ComposerProviderModel[];
}

export interface ComposerProviderModel {
  key: string;
  name?: string | null;
  provider_model_id?: string | null;
  enabled?: boolean;
}

export interface ComposerSelectableModel {
  ref: string;
  providerKey: string;
  providerName: string;
  modelKey: string;
  modelName: string;
  providerModelId: string;
}

export const REASONING_LEVELS: ComposerReasoningOption[] = [
  {
    id: "flash",
    labelKey: "chat:reasoning.flash",
    fallback: "Flash",
    descriptionKey: "chat:reasoning.flashDescription",
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
      "agent.presentation.write",
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
  flash: "none",
  thinking: "low",
  pro: "medium",
  ultra: "high",
};

const MODE_FLAGS: Record<
  ComposerMode,
  { thinking_enabled: boolean; is_plan_mode: boolean; subagent_enabled: boolean }
> = {
  flash: { thinking_enabled: false, is_plan_mode: false, subagent_enabled: false },
  thinking: { thinking_enabled: true, is_plan_mode: false, subagent_enabled: false },
  pro: { thinking_enabled: true, is_plan_mode: true, subagent_enabled: false },
  ultra: { thinking_enabled: true, is_plan_mode: true, subagent_enabled: true },
};

export function normalizeComposerMode(value: string | null | undefined): ComposerMode {
  if (value === "quick" || value === "chat") return "flash";
  if (value === "auto") return "thinking";
  if (value === "plan") return "pro";
  return REASONING_LEVEL_IDS.has(value as ComposerReasoningLevel)
    ? (value as ComposerReasoningLevel)
    : "pro";
}

export function normalizeReasoningLevel(
  value: string | null | undefined,
): ComposerReasoningLevel {
  if (value === "quick") return "flash";
  return REASONING_LEVEL_IDS.has(value as ComposerReasoningLevel)
    ? (value as ComposerReasoningLevel)
    : "pro";
}

export function composerModeForReasoningLevel(
  value: string | null | undefined,
): ComposerMode {
  return normalizeReasoningLevel(value);
}

export function reasoningLevelForComposerMode(
  value: string | null | undefined,
): ComposerReasoningLevel {
  return normalizeComposerMode(value);
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
  modelRefValue: string | null,
  mode: string,
  reasoningLevel: string | null | undefined,
): AgentRunHarnessOptions | undefined {
  const normalizedMode = normalizeComposerMode(mode);
  const normalizedReasoning = normalizeReasoningLevel(reasoningLevel ?? normalizedMode);
  const selectedMode =
    mode === "auto" || mode === "plan" || mode === "chat"
      ? normalizedReasoning
      : normalizedMode;
  const modeFlags = MODE_FLAGS[selectedMode];
  const reasoningEffort = reasoningEffortForReasoningLevel(selectedMode);
  const harnessOptions: AgentRunHarnessOptions & {
    mode?: ComposerMode;
    thinking_enabled?: boolean;
    is_plan_mode?: boolean;
    subagent_enabled?: boolean;
    model_reasoning_effort?: ComposerModelReasoningEffort;
  } = {
    mode: selectedMode,
    ...modeFlags,
    model_capabilities: {
      vision: false,
      thinking: modeFlags.thinking_enabled,
    },
    model_reasoning_effort: reasoningEffort,
  };
  if (modelRefValue) {
    harnessOptions.model_ref = modelRefValue;
  }
  return Object.keys(harnessOptions).length > 0 ? harnessOptions : undefined;
}

export function modelRef(providerKey: string, modelKey: string): string {
  return `${providerKey}/${modelKey}`;
}

export function flattenUsableModels(
  providers: ComposerModelProvider[] | null | undefined,
): ComposerSelectableModel[] {
  return (providers ?? []).flatMap((provider) => {
    if (provider.enabled === false) return [];
    return (provider.models ?? [])
      .filter((model) => model.enabled !== false && Boolean(model.provider_model_id?.trim()))
      .map((model) => ({
        ref: modelRef(provider.key, model.key),
        providerKey: provider.key,
        providerName: provider.name || provider.key,
        modelKey: model.key,
        modelName: model.name || model.provider_model_id || model.key,
        providerModelId: model.provider_model_id || model.key,
      }));
  });
}

export function selectUsableModelRef(
  providers: ComposerModelProvider[] | null | undefined,
  currentRef: string | null | undefined,
): string {
  const usable = flattenUsableModels(providers);
  if (currentRef && usable.some((model) => model.ref === currentRef)) return currentRef;
  return usable[0]?.ref ?? "";
}

export function buildComposerScopes(policyId: string | null | undefined): string[] {
  return [...getPermissionPolicy(policyId).scopes];
}

export function hasConfiguredModelProfile(profile: ComposerModelProfile): boolean {
  return Boolean(profile.model?.trim());
}

export function isUsableModelProfile(profile: ComposerModelProfile): boolean {
  return profile.enabled !== false && hasConfiguredModelProfile(profile);
}

export function selectUsableModelProfileKey(
  profiles: ComposerModelProfile[] | null | undefined,
  currentKey: string | null | undefined,
): string {
  const usable = profiles?.filter(isUsableModelProfile) ?? [];
  if (currentKey && usable.some((profile) => profile.key === currentKey)) return currentKey;
  return usable[0]?.key ?? "";
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
  flash: { labelKey: "chat:modeFlash", fallback: "Flash" },
  thinking: { labelKey: "chat:modeThinking", fallback: "Thinking" },
  pro: { labelKey: "chat:modePro", fallback: "Pro" },
  ultra: { labelKey: "chat:modeUltra", fallback: "Ultra" },
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
