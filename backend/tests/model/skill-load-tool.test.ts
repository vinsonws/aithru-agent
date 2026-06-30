import { describe, expect, it } from "vitest";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import { ModelTurnLoop } from "@aithru-agent/harness";
import { TestModelAdapter } from "@aithru-agent/model";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import { SkillRegistry, SkillResolver } from "@aithru-agent/skills";

describe("skill.load", () => {
  it("loads a visible skill once and includes it on the next model turn", async () => {
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
    const run = {
      id: "run_skill_load",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "chat" as const,
      thread_id: null,
      workspace_id: "ws_1",
      task_msg: "Research this",
      scopes: ["*"],
      harness_options: { model_profile_key: "default" },
      status: "queued" as const,
      current_approval_id: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    };
    store.createRun(run);

    let secondTurnSystem = "";
    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter: new ProductionCapabilityRouter(store, eventWriter, resolver),
      skillResolver: resolver,
      modelAdapter: new TestModelAdapter([
        [{ type: "tool_call", id: "load_1", name: "skill.load", input: { key: "deep-research" } }],
        (input) => {
          secondTurnSystem = input.messages.find((m) => m.role === "system")?.content ?? "";
          return [{ type: "text_delta", delta: "done" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute(run);

    expect(secondTurnSystem).toContain("Deep Research");
    expect(secondTurnSystem).toContain("Use evidence and cite sources.");
    expect(store.listEvents(run.id).filter((event) => event.type === EVENT_TYPES.SKILL_ACTIVATED)).toHaveLength(1);
  });
});
