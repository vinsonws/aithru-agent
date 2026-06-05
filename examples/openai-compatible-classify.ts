import type { AgentEvent, AgentHost } from "@aithru/agent-core";
import { OpenAICompatibleAgentModelAdapter } from "@aithru/agent-model-openai-compatible";
import { AgentRuntime } from "@aithru/agent-runtime";

const baseUrl = process.env.AITHRU_OPENAI_COMPATIBLE_BASE_URL?.trim();
const modelName = process.env.AITHRU_OPENAI_COMPATIBLE_MODEL?.trim();
const apiKey = process.env.AITHRU_OPENAI_COMPATIBLE_API_KEY?.trim();

if (!baseUrl || !modelName) {
  console.log(
    "Skipping real-provider example. Set AITHRU_OPENAI_COMPATIBLE_BASE_URL and AITHRU_OPENAI_COMPATIBLE_MODEL to run it.",
  );
} else {
  const events: AgentEvent[] = [];
  const host: AgentHost = {
    emit(event) {
      events.push(event);
      console.log(event.type);
    },
    async callTool(request) {
      throw new Error(
        `Unexpected tool call in classify real-provider example: ${request.toolName}`,
      );
    },
  };

  const model = new OpenAICompatibleAgentModelAdapter({
    baseUrl,
    ...(apiKey ? { apiKey } : {}),
    model: modelName,
    defaultSystemPrompt: [
      "You are an Aithru Agent classification model.",
      "Return only JSON. Do not include markdown.",
      "Classify the task into one of these routes: direct, research.",
      "Return either plain JSON with route, confidence, and reason, or a structured.output event envelope.",
    ].join("\n"),
  });

  const output = await new AgentRuntime().runTask("classify", {
    task: {
      id: "task_openai_compatible_classify_demo",
      goal: [
        "Classify this request into direct or research.",
        "Return JSON like:",
        '{"route":"research","confidence":0.8,"reason":"..."}',
        "or:",
        '{"type":"structured.output","value":{"route":"research","confidence":0.8,"reason":"..."}}',
      ].join("\n"),
      input: {
        request:
          "Compare Aithru Agent with DeerFlow and identify architectural tradeoffs.",
      },
      outputSchema: {
        type: "object",
        required: ["route", "confidence", "reason"],
        properties: {
          route: { type: "string", enum: ["direct", "research"] },
          confidence: { type: "number" },
          reason: { type: "string" },
        },
      },
    },
    model,
    host,
  });

  console.log(JSON.stringify(output.metadata?.classification ?? output, null, 2));
  console.log(`received ${events.length} agent events`);
}
