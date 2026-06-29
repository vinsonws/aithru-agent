import { describe, expect, it } from "vitest";
import {
  AnthropicCompatibleAdapter,
  OpenAICompatibleAdapter,
  collectModelEvents,
} from "@aithru-agent/model";

const input = {
  run: {} as any,
  messages: [],
  context: {},
  toolResults: [],
};

describe("provider model adapters", () => {
  it("normalizes OpenAI-compatible events into Aithru model events", async () => {
    const adapter = new OpenAICompatibleAdapter(() => [
      { type: "response.output_text.delta", delta: "Hello" },
      {
        type: "response.output_item.done",
        item: {
          type: "function_call",
          call_id: "call_1",
          name: "todo.create",
          arguments: '{"title":"x"}',
        },
      },
      {
        type: "response.completed",
        response: { usage: { input_tokens: 1, output_tokens: 2, total_tokens: 3 } },
      },
    ]);

    const events = await collectModelEvents(adapter.createTurn(input));
    expect(events).toEqual([
      { type: "text_delta", delta: "Hello" },
      { type: "tool_call", id: "call_1", name: "todo.create", input: { title: "x" } },
      { type: "usage", inputTokens: 1, outputTokens: 2, totalTokens: 3 },
      { type: "completed", content: undefined },
    ]);
  });

  it("normalizes Anthropic-compatible events into Aithru model events", async () => {
    const adapter = new AnthropicCompatibleAdapter(() => [
      { type: "content_block_delta", delta: { type: "text_delta", text: "Hi" } },
      {
        type: "content_block_start",
        content_block: {
          type: "tool_use",
          id: "toolu_1",
          name: "todo.create",
          input: { title: "y" },
        },
      },
      { type: "message_delta", usage: { input_tokens: 4, output_tokens: 5 } },
      { type: "message_stop" },
    ]);

    const events = await collectModelEvents(adapter.createTurn(input));
    expect(events).toEqual([
      { type: "text_delta", delta: "Hi" },
      { type: "tool_call", id: "toolu_1", name: "todo.create", input: { title: "y" } },
      { type: "usage", inputTokens: 4, outputTokens: 5, totalTokens: undefined },
      { type: "completed" },
    ]);
  });
});
