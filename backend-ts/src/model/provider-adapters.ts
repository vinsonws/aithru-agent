import type {
  AgentModelAdapter,
  AgentModelTurnInput,
  ModelTurnEvent,
} from "./types.js";

export type ProviderFetch = (
  input: AgentModelTurnInput,
) => Promise<unknown[]> | unknown[];

function parseToolInput(value: unknown): Record<string, unknown> {
  if (value == null) return {};
  if (typeof value === "string") {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : {};
  }
  return typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export class OpenAICompatibleAdapter implements AgentModelAdapter {
  constructor(private fetchEvents: ProviderFetch) {}

  async *createTurn(input: AgentModelTurnInput): AsyncIterable<ModelTurnEvent> {
    const events = await this.fetchEvents(input);
    for (const event of events as any[]) {
      if (event.type === "response.output_text.delta") {
        yield { type: "text_delta", delta: String(event.delta ?? "") };
      } else if (event.type === "response.reasoning.delta") {
        yield { type: "reasoning_delta", delta: String(event.delta ?? "") };
      } else if (
        event.type === "response.output_item.done" &&
        event.item?.type === "function_call"
      ) {
        yield {
          type: "tool_call",
          id: String(event.item.call_id ?? event.item.id),
          name: String(event.item.name),
          input: parseToolInput(event.item.arguments),
        };
      } else if (event.type === "response.completed") {
        const usage = event.response?.usage;
        if (usage) {
          yield {
            type: "usage",
            inputTokens: Number(usage.input_tokens ?? 0),
            outputTokens: Number(usage.output_tokens ?? 0),
            totalTokens:
              usage.total_tokens == null ? undefined : Number(usage.total_tokens),
          };
        }
        yield { type: "completed", content: event.response?.output_text };
      } else if (event.type === "response.failed") {
        yield {
          type: "failed",
          error: {
            code: String(event.error?.code ?? "MODEL_ERROR"),
            message: String(event.error?.message ?? "Model request failed"),
            retryable: Boolean(event.error?.retryable),
          },
        };
      }
    }
  }
}

export class AnthropicCompatibleAdapter implements AgentModelAdapter {
  constructor(private fetchEvents: ProviderFetch) {}

  async *createTurn(input: AgentModelTurnInput): AsyncIterable<ModelTurnEvent> {
    const events = await this.fetchEvents(input);
    for (const event of events as any[]) {
      if (event.type === "content_block_delta" && event.delta?.type === "text_delta") {
        yield { type: "text_delta", delta: String(event.delta.text ?? "") };
      } else if (
        event.type === "content_block_delta" &&
        event.delta?.type === "thinking_delta"
      ) {
        yield { type: "reasoning_delta", delta: String(event.delta.thinking ?? "") };
      } else if (
        event.type === "content_block_start" &&
        event.content_block?.type === "tool_use"
      ) {
        yield {
          type: "tool_call",
          id: String(event.content_block.id),
          name: String(event.content_block.name),
          input: parseToolInput(event.content_block.input),
        };
      } else if (event.type === "message_delta" && event.usage) {
        yield {
          type: "usage",
          inputTokens: Number(event.usage.input_tokens ?? 0),
          outputTokens: Number(event.usage.output_tokens ?? 0),
          totalTokens:
            event.usage.total_tokens == null
              ? undefined
              : Number(event.usage.total_tokens),
        };
      } else if (event.type === "message_stop") {
        yield { type: "completed" };
      } else if (event.type === "error") {
        yield {
          type: "failed",
          error: {
            code: String(event.error?.type ?? "MODEL_ERROR"),
            message: String(event.error?.message ?? "Model request failed"),
            retryable: false,
          },
        };
      }
    }
  }
}
