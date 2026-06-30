import { describe, expect, it } from "vitest";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { ModelTurnLoop, emitSkillActivated } from "@aithru-agent/harness";
import type { AgentModelToolResult } from "@aithru-agent/model";
import { TestModelAdapter } from "@aithru-agent/model";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import { SkillRegistry, SkillResolver } from "@aithru-agent/skills";

let runCounter = 0;

function createRun(): AgentRun {
  runCounter += 1;
  return {
    id: `run_skill_load_${runCounter}`,
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "chat",
    thread_id: null,
    workspace_id: "ws_1",
    task_msg: "Research this",
    scopes: ["*"],
    harness_options: { model_profile_key: "default" },
    status: "queued",
    current_approval_id: null,
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    claim: null,
    result: null,
    error: null,
  };
}

async function executeSkillLoad(input: Record<string, unknown>, preactivate = false) {
  const store = new InMemoryStore();
  const registry = new SkillRegistry();
  registry.register({
    key: "deep-research",
    path: "/skills/deep-research",
    name: "Deep Research",
    description: "Research with evidence.",
    version: "0.0.0",
    status: "published",
    enabled: true,
    allowed_tools: [],
    denied_tools: [],
    instructions: "Use evidence and cite sources.",
    resources: { references: [], scripts: [], assets: [], examples: [] },
  });
  const resolver = new SkillResolver(registry, store);
  const eventWriter = new AgentEventWriter(store);
  const run = createRun();
  store.createRun(run);
  if (preactivate) {
    emitSkillActivated({
      eventWriter,
      runId: run.id,
      threadId: run.thread_id ?? null,
      key: "deep-research",
      name: "Deep Research",
      source: "builtin",
      version: "0.0.0",
      trigger: "explicit",
      allowedTools: [],
      deniedTools: [],
    });
  }

  let secondTurnSystem = "";
  let toolResults: AgentModelToolResult[] = [];
  const loop = new ModelTurnLoop({
    store,
    eventWriter,
    capabilityRouter: new ProductionCapabilityRouter(store, eventWriter, resolver),
    skillResolver: resolver,
    modelAdapter: new TestModelAdapter([
      [{ type: "tool_call", id: "load_1", name: "skill.load", input }],
      (turnInput) => {
        secondTurnSystem = turnInput.messages.find((message) => message.role === "system")?.content ?? "";
        toolResults = turnInput.toolResults;
        return [{ type: "text_delta", delta: "done" }, { type: "completed" }];
      },
    ]),
  });

  const completedRun = await loop.execute(run);
  return { completedRun, run, secondTurnSystem, store, toolResults };
}

describe("skill.load", () => {
  it("loads a visible skill once and includes it on the next model turn", async () => {
    const { secondTurnSystem, store, toolResults, run } = await executeSkillLoad({ key: "deep-research" });

    expect(toolResults[0]?.output).toEqual({ loaded: true, key: "deep-research" });
    expect(secondTurnSystem).toContain("Deep Research");
    expect(secondTurnSystem).toContain("Use evidence and cite sources.");
    expect(store.listEvents(run.id).filter((event) => event.type === EVENT_TYPES.SKILL_ACTIVATED)).toHaveLength(1);
  });

  it("does not emit a duplicate activation for an already active skill", async () => {
    const { store, toolResults, run } = await executeSkillLoad({ key: "deep-research" }, true);

    expect(toolResults[0]?.output).toEqual({ loaded: true, key: "deep-research" });
    expect(store.listEvents(run.id).filter((event) => event.type === EVENT_TYPES.SKILL_ACTIVATED)).toHaveLength(1);
  });

  it("returns a structured error for an unknown skill without failing the run", async () => {
    const { completedRun, store, toolResults, run } = await executeSkillLoad({ key: "missing-skill" });

    expect(toolResults[0]?.output).toEqual({
      loaded: false,
      key: "missing-skill",
      error: "Skill not found: missing-skill",
    });
    expect(completedRun.status).toBe("completed");
    expect(store.listEvents(run.id).filter((event) => event.type === EVENT_TYPES.RUN_FAILED)).toHaveLength(0);
    expect(store.listEvents(run.id).filter((event) => event.type === EVENT_TYPES.SKILL_ACTIVATED)).toHaveLength(0);
  });

  it.each([{}, { key: "   " }])("requires a non-empty key for %j without failing the run", async (input) => {
    const { completedRun, store, toolResults, run } = await executeSkillLoad(input);

    expect(toolResults[0]?.output).toEqual({ loaded: false, error: "key is required" });
    expect(completedRun.status).toBe("completed");
    expect(store.listEvents(run.id).filter((event) => event.type === EVENT_TYPES.RUN_FAILED)).toHaveLength(0);
    expect(store.listEvents(run.id).filter((event) => event.type === EVENT_TYPES.SKILL_ACTIVATED)).toHaveLength(0);
  });
});
