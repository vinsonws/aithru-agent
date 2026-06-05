import type { AgentModelAdapter, AgentModelInput } from "@aithru/agent-core";
import {
  ScriptedModelAdapter,
  createStaticFinalModel,
  createStaticStructuredModel,
} from "./index.js";
import { describe, expect, test } from "vitest";

const modelInput: AgentModelInput = {
  task: {
    id: "task_test",
    goal: "Test deterministic model output.",
  },
  mode: "classify",
};

async function collectEvents(model: AgentModelAdapter) {
  const events = [];

  for await (const event of model.generate(modelInput)) {
    events.push(event);
  }

  return events;
}

describe("ScriptedModelAdapter", () => {
  test("outputs scripted events in order", async () => {
    const model = new ScriptedModelAdapter({
      events: [
        { type: "text.delta", text: "hello" },
        { type: "structured.output", value: { route: "research" } },
        { type: "final", output: "done" },
      ],
    });

    await expect(collectEvents(model)).resolves.toEqual([
      { type: "text.delta", text: "hello" },
      { type: "structured.output", value: { route: "research" } },
      { type: "final", output: "done" },
    ]);
  });
});

describe("static model helpers", () => {
  test("createStaticStructuredModel outputs one structured output event", async () => {
    const value = { route: "simple", confidence: 1 };

    await expect(collectEvents(createStaticStructuredModel(value))).resolves.toEqual([
      { type: "structured.output", value },
    ]);
  });

  test("createStaticFinalModel outputs one final event", async () => {
    const output = { summary: "complete" };

    await expect(collectEvents(createStaticFinalModel(output))).resolves.toEqual([
      { type: "final", output },
    ]);
  });
});
