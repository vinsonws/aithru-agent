import { describe, expect, it } from "vitest";
import { ProductionCapabilityRouter } from "../../src/capabilities/production-router.js";
import type { AgentRun } from "@aithru-agent/contracts";
import { ModelTurnLoop } from "../../src/core/model-turn.js";
import { TestModelAdapter } from "../../src/model/test-adapter.js";
import { InMemoryStore } from "../../src/persistence/store.js";
import { AgentEventWriter } from "@aithru-agent/stream";

function createRun(): AgentRun {
  return {
    id: "run_model",
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    skill_id: null,
    workspace_id: "ws_model",
    task_msg: "Create a todo",
    scopes: ["*"],
    harness_options: null,
    status: "queued",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
  };
}

describe("ModelTurnLoop", () => {
  it("routes model tool calls through the CapabilityRouter and records usage", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun(run);

    const modelAdapter = new TestModelAdapter([
      [
        { type: "text_delta", delta: "I will create a todo." },
        {
          type: "tool_call",
          id: "model_tc_1",
          name: "todo.create",
          input: { title: "From model" },
        },
        { type: "usage", inputTokens: 12, outputTokens: 8, totalTokens: 20 },
        { type: "completed" },
      ],
      (input) => [
        {
          type: "text_delta",
          delta: ` Tool result count: ${input.toolResults.length}. Done.`,
        },
        { type: "completed" },
      ],
    ]);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter,
    });

    const completed = await loop.execute(run);
    expect(completed.status).toBe("completed");
    expect(store.listTodos(run.id)[0].title).toBe("From model");

    const eventTypes = store.listEvents(run.id).map((event) => event.type);
    expect(eventTypes).toContain("model.usage");
    expect(eventTypes).toContain("tool.proposed");
    expect(eventTypes).toContain("tool.completed");
    expect(eventTypes).toContain("run.completed");
  });
});
