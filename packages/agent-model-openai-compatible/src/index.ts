import type {
  AgentError,
  AgentModelAdapter,
  AgentModelEvent,
  AgentModelInput,
  AgentRiskLevel,
  AgentToolRequest,
} from "@aithru/agent-core";

export type OpenAICompatibleAgentModelAdapterOptions = {
  name?: string;
  baseUrl: string;
  apiKey?: string;
  model: string;
  defaultSystemPrompt?: string;
  timeoutMs?: number;
  headers?: Record<string, string>;
};

type ChatMessage = {
  role: "system" | "user";
  content: string;
};

export class OpenAICompatibleAgentModelAdapter implements AgentModelAdapter {
  readonly name: string;

  private readonly apiKey: string | undefined;
  private readonly baseUrl: string;
  private readonly defaultSystemPrompt: string | undefined;
  private readonly headers: Record<string, string>;
  private readonly model: string;
  private readonly timeoutMs: number | undefined;

  constructor(options: OpenAICompatibleAgentModelAdapterOptions) {
    this.name = options.name ?? "openai-compatible-agent-model";
    this.apiKey = options.apiKey;
    this.baseUrl = normalizeBaseUrl(options.baseUrl);
    this.defaultSystemPrompt = options.defaultSystemPrompt;
    this.headers = options.headers ?? {};
    this.model = options.model;
    this.timeoutMs = options.timeoutMs;
  }

  async *generate(input: AgentModelInput): AsyncIterable<AgentModelEvent> {
    const controller = this.timeoutMs === undefined ? undefined : new AbortController();
    const timeout =
      controller === undefined
        ? undefined
        : setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(`${this.baseUrl}/chat/completions`, {
        method: "POST",
        headers: this.buildHeaders(),
        body: JSON.stringify({
          model: this.model,
          messages: this.buildMessages(input),
        }),
        ...(controller === undefined ? {} : { signal: controller.signal }),
      });

      if (!response.ok) {
        const responseBody = await response.text();
        throw new Error(
          `OpenAI-compatible request failed with status ${response.status}${formatStatusText(
            response.statusText,
          )}: ${previewBody(responseBody)}`,
        );
      }

      const responseBody = (await response.json()) as unknown;
      const content = getMessageContent(responseBody);

      for (const event of parseModelContent(content)) {
        yield event;
      }
    } finally {
      if (timeout !== undefined) {
        clearTimeout(timeout);
      }
    }
  }

  private buildHeaders() {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...this.headers,
    };

    if (this.apiKey !== undefined) {
      headers.Authorization = `Bearer ${this.apiKey}`;
    }

    return headers;
  }

  private buildMessages(input: AgentModelInput): ChatMessage[] {
    const messages: ChatMessage[] = [];

    if (this.defaultSystemPrompt !== undefined) {
      messages.push({ role: "system", content: this.defaultSystemPrompt });
    }

    messages.push({
      role: "user",
      content: buildUserPrompt(input),
    });

    return messages;
  }
}

function normalizeBaseUrl(baseUrl: string) {
  return baseUrl.replace(/\/+$/, "");
}

function buildUserPrompt(input: AgentModelInput) {
  const sections = [
    ["Task goal", input.task.goal],
    ["Mode", input.mode],
  ];

  if (input.task.input !== undefined) {
    sections.push(["Task input", formatValue(input.task.input)]);
  }

  if (input.step !== undefined) {
    sections.push(["Step objective", input.step.objective]);
  }

  if (input.tools !== undefined) {
    sections.push(["Available tools", formatValue(input.tools)]);
  }

  if (input.outputSchema !== undefined) {
    sections.push(["Output schema", formatValue(input.outputSchema)]);
  }

  return sections.map(([label, value]) => `${label}:\n${value}`).join("\n\n");
}

function formatValue(value: unknown) {
  return JSON.stringify(value, null, 2) ?? String(value);
}

function formatStatusText(statusText: string) {
  return statusText.length === 0 ? "" : ` ${statusText}`;
}

function previewBody(body: string) {
  const normalized = body.replace(/\s+/g, " ").trim();

  if (normalized.length === 0) {
    return "<empty response body>";
  }

  return normalized.length > 200 ? `${normalized.slice(0, 200)}...` : normalized;
}

function getMessageContent(responseBody: unknown) {
  if (!isRecord(responseBody) || !Array.isArray(responseBody.choices)) {
    throw missingContentError();
  }

  const firstChoice = responseBody.choices[0];

  if (!isRecord(firstChoice) || !isRecord(firstChoice.message)) {
    throw missingContentError();
  }

  if (typeof firstChoice.message.content !== "string") {
    throw missingContentError();
  }

  return firstChoice.message.content;
}

function missingContentError() {
  return new Error(
    "OpenAI-compatible response did not include choices[0].message.content",
  );
}

function parseModelContent(content: string): AgentModelEvent[] {
  let parsed: unknown;

  try {
    parsed = JSON.parse(content) as unknown;
  } catch {
    return [{ type: "final", output: content }];
  }

  if (isRecord(parsed) && typeof parsed.type === "string") {
    return [parseModelEvent(parsed)];
  }

  if (isRecord(parsed) && Array.isArray(parsed.events)) {
    return parsed.events.map((event) => parseModelEvent(event));
  }

  return [{ type: "structured.output", value: parsed }];
}

function parseModelEvent(event: unknown): AgentModelEvent {
  if (!isRecord(event)) {
    return invalidModelEvent("Model event must be an object.");
  }

  switch (event.type) {
    case "text.delta":
      return typeof event.text === "string"
        ? { type: "text.delta", text: event.text }
        : invalidModelEvent("text.delta event must include string text.");

    case "structured.output":
      return hasOwn(event, "value")
        ? { type: "structured.output", value: event.value }
        : invalidModelEvent("structured.output event must include value.");

    case "tool_call.proposed": {
      const toolCall = parseToolCall(event.toolCall);

      return toolCall === undefined
        ? invalidModelEvent("tool_call.proposed event must include a valid toolCall.")
        : { type: "tool_call.proposed", toolCall };
    }

    case "final":
      return hasOwn(event, "output")
        ? { type: "final", output: event.output }
        : invalidModelEvent("final event must include output.");

    case "error": {
      const error = parseAgentError(event.error);

      return error === undefined
        ? invalidModelEvent("error event must include a valid error.")
        : { type: "error", error };
    }

    default:
      return typeof event.type === "string"
        ? invalidModelEvent(`Unknown model event type "${event.type}".`)
        : invalidModelEvent("Model event must include a string type.");
  }
}

function parseToolCall(value: unknown): AgentToolRequest | undefined {
  if (!isRecord(value)) {
    return undefined;
  }

  if (
    typeof value.id !== "string" ||
    typeof value.toolName !== "string" ||
    !hasOwn(value, "arguments")
  ) {
    return undefined;
  }

  return {
    id: value.id,
    toolName: value.toolName,
    arguments: value.arguments,
    ...(typeof value.reason === "string" ? { reason: value.reason } : {}),
    ...(typeof value.stepId === "string" ? { stepId: value.stepId } : {}),
    ...(isRiskLevel(value.riskLevel) ? { riskLevel: value.riskLevel } : {}),
  };
}

function parseAgentError(value: unknown): AgentError | undefined {
  if (!isRecord(value) || typeof value.code !== "string" || typeof value.message !== "string") {
    return undefined;
  }

  return {
    code: value.code,
    message: value.message,
    ...(hasOwn(value, "cause") ? { cause: value.cause } : {}),
    ...(isRecord(value.metadata) ? { metadata: value.metadata } : {}),
  };
}

function invalidModelEvent(message: string): AgentModelEvent {
  return {
    type: "error",
    error: {
      code: "invalid_model_event",
      message,
    },
  };
}

function isRiskLevel(value: unknown): value is AgentRiskLevel {
  return (
    value === "safe" ||
    value === "read" ||
    value === "write" ||
    value === "dangerous"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOwn(value: Record<string, unknown>, key: string) {
  return Object.prototype.hasOwnProperty.call(value, key);
}
