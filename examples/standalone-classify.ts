import type { AgentEvent, AgentHost } from "@aithru/agent-core";
import { AgentRuntime } from "@aithru/agent-runtime";
import { createStaticStructuredModel } from "@aithru/model-test";

const events: AgentEvent[] = [];

const host: AgentHost = {
  emit(event) {
    events.push(event);
  },
  async callTool(request) {
    return {
      id: request.id,
      toolName: request.toolName,
      output: { ok: true },
    };
  },
};

const model = createStaticStructuredModel({
  route: "research",
  confidence: 0.92,
  reason: "The request needs multi-step analysis.",
});

const runtime = new AgentRuntime();

const input = {
  task: {
    id: "task_classify_demo",
    goal: "Classify the request into simple or research.",
    input: "Compare Aithru Agent with DeerFlow.",
  },
  model,
  host,
};

for await (const event of runtime.run("classify", input)) {
  console.log(event.type);
}

console.log(JSON.stringify(events.at(-1), null, 2));

const output = await runtime.runTask("classify", input);
console.log(output.summary);
