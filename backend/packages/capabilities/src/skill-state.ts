import type { AgentStreamEvent } from "@aithru-agent/contracts";
import { EVENT_TYPES } from "@aithru-agent/stream";

export interface SkillPolicySnapshot {
  allowed_tools: string[];
  denied_tools: string[];
}

export function activeSkillKeysFromEvents(events: AgentStreamEvent[]): string[] {
  const keys: string[] = [];
  for (const event of events) {
    if (event.type !== EVENT_TYPES.SKILL_ACTIVATED) continue;
    const key = (event.payload as any)?.key;
    if (typeof key === "string" && key && !keys.includes(key)) keys.push(key);
  }
  return keys;
}

export function skillPolicySnapshotsFromEvents(
  events: AgentStreamEvent[],
): SkillPolicySnapshot[] | null {
  const snapshots: SkillPolicySnapshot[] = [];
  for (const event of events) {
    if (event.type !== EVENT_TYPES.SKILL_ACTIVATED) continue;
    const policy = policySnapshot((event.payload as any)?.policy);
    if (!policy) return null;
    snapshots.push(policy);
  }
  return snapshots;
}

function policySnapshot(value: unknown): SkillPolicySnapshot | null {
  if (!isRecord(value)) return null;
  const allowed_tools = stringArray(value.allowed_tools);
  const denied_tools = stringArray(value.denied_tools);
  if (!allowed_tools || !denied_tools) return null;
  return { allowed_tools, denied_tools };
}

function stringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  return value.every((item) => typeof item === "string") ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
