import type { AgentRunHarnessOptions } from "@/lib/api";

export type ComposerMode = "auto" | "plan" | "chat";
export type ComposerPermissionPolicyId = "ask" | "auto_safe" | "read_only";

export interface ComposerPermissionPolicy {
  id: ComposerPermissionPolicyId;
  labelKey: string;
  fallback: string;
  descriptionKey: string;
  fallbackDescription: string;
  scopes: string[];
}

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
      "agent.artifact.write",
      "agent.research.write",
      "agent.input.write",
      "agent.memory.read",
    ],
  },
  {
    id: "auto_safe",
    labelKey: "chat:permission.autoSafe",
    fallback: "Auto-safe",
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

export function normalizeComposerMode(value: string | null | undefined): ComposerMode {
  return value === "plan" || value === "chat" || value === "auto" ? value : "auto";
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
): AgentRunHarnessOptions | undefined {
  const normalizedMode = normalizeComposerMode(mode);
  const harnessOptions: AgentRunHarnessOptions = {};
  if (profileKey && profileKey !== "__default__") {
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
