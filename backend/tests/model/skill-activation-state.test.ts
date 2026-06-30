import { describe, expect, it } from "vitest";
import type { AgentStreamEvent } from "@aithru-agent/contracts";
import { activeSkillKeysFromEvents } from "@aithru-agent/capabilities";

function event(sequence: number, key: string): AgentStreamEvent {
  return {
    id: `evt_${sequence}`,
    run_id: "run_1",
    thread_id: null,
    sequence,
    timestamp: "2026-01-01T00:00:00Z",
    type: "skill.activated",
    source: { kind: "harness", id: null, name: null },
    visibility: "audit",
    redaction: "none",
    summary: null,
    payload: { key, trigger: "explicit" },
  };
}

describe("skill activation state", () => {
  it("projects ordered unique active skill keys from events", () => {
    expect(activeSkillKeysFromEvents([
      event(1, "deep-research"),
      event(2, "file-report"),
      event(3, "deep-research"),
    ])).toEqual(["deep-research", "file-report"]);
  });
});
