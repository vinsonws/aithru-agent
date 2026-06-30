import type { AgentStreamEvent } from "@aithru-agent/contracts";
import { EVENT_TYPES } from "@aithru-agent/stream";

export function activeSkillKeysFromEvents(events: AgentStreamEvent[]): string[] {
  const keys: string[] = [];
  for (const event of events) {
    if (event.type !== EVENT_TYPES.SKILL_ACTIVATED) continue;
    const key = (event.payload as any)?.key;
    if (typeof key === "string" && key && !keys.includes(key)) keys.push(key);
  }
  return keys;
}
