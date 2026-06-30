import { describe, expect, it } from "vitest";
import {
  buildAnthropicMessagesRequest,
  buildOpenAIChatCompletionRequest,
  buildOpenAIResponsesRequest,
  collectModelEvents,
  OpenAISdkModelAdapter,
  resolveModelApiKind,
} from "@aithru-agent/model";

function input(effort: string = "none") {
  return {
    run: {
      id: "run_sdk",
      task_msg: "Hello",
      harness_options: {
        instructions: "Be concise.",
        model_reasoning_effort: effort,
      },
    } as any,
    messages: [
      {
        id: "msg_user",
        thread_id: "thread_sdk",
        role: "user",
        content: "Hello",
        run_id: "run_sdk",
        workspace_paths: [],
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    context: {},
    tools: [],
    toolResults: [],
  };
}

function inputWithTools() {
  return {
    ...input(),
    tools: [
      {
        name: "todo.create",
        description: "Create a todo",
        input_schema: {
          type: "object",
          properties: { title: { type: "string" } },
          required: ["title"],
        },
      },
    ],
  } as any;
}

describe("SDK model adapters", () => {
  it("chooses API kind from provider and metadata", () => {
    expect(resolveModelApiKind("custom", null)).toBe("openai_chat_completions");
    expect(resolveModelApiKind("anthropic", null)).toBe("anthropic_messages");
    expect(resolveModelApiKind("openai", { use_responses_api: true })).toBe(
      "openai_responses",
    );
  });

  it("merges OpenAI-compatible thinking params only when thinking is enabled", () => {
    const request = buildOpenAIChatCompletionRequest(
      {
        apiKey: "test",
        provider: "custom",
        model: "custom:deepseek-reasoner",
        metadata: {
          request: { max_tokens: 8192, temperature: 0.7 },
          supports_thinking: true,
          supports_reasoning_effort: true,
          when_thinking_enabled: {
            extra_body: { thinking: { type: "enabled" } },
          },
        },
      },
      input("low"),
    );

    expect(request).toMatchObject({
      model: "deepseek-reasoner",
      max_tokens: 8192,
      temperature: 0.7,
      reasoning_effort: "low",
      extra_body: { thinking: { type: "enabled" } },
      stream: true,
      stream_options: { include_usage: true },
    });
  });

  it("uses profile thinking capability as the default OpenAI-compatible thinking body", () => {
    const request = buildOpenAIChatCompletionRequest(
      {
        apiKey: "test",
        provider: "custom",
        model: "custom:deepseek-v4-flash",
        capabilities: { thinking: true },
        metadata: { base_url: "https://api.deepseek.com/v1" },
      },
      input("medium"),
    );

    expect(request).toMatchObject({
      model: "deepseek-v4-flash",
      extra_body: { thinking: { type: "enabled" } },
      stream: true,
    });
  });

  it("rewrites Qwen thinking flags for local OpenAI-compatible gateways", () => {
    const request = buildOpenAIChatCompletionRequest(
      {
        apiKey: "test",
        provider: "custom",
        model: "Qwen/Qwen3.5",
        metadata: {
          compat: "qwen",
          supports_thinking: true,
          when_thinking_enabled: {
            extra_body: { thinking: { type: "enabled" } },
          },
        },
      },
      input("none"),
    );

    expect(request.extra_body).toEqual({
      chat_template_kwargs: { enable_thinking: false },
    });
    expect(request).not.toHaveProperty("reasoning_effort");
  });

  it("uses Anthropic system and direct thinking params", () => {
    const request = buildAnthropicMessagesRequest(
      {
        apiKey: "test",
        provider: "anthropic",
        model: "claude-test",
        metadata: {
          supports_thinking: true,
          when_thinking_enabled: {
            thinking: { type: "enabled", budget_tokens: 1024 },
          },
        },
      },
      input("none"),
    );

    expect(request).toMatchObject({
      model: "claude-test",
      max_tokens: 4096,
      system: "Be concise.",
      thinking: { type: "disabled" },
      stream: true,
    });
    expect(request.messages).toEqual([{ role: "user", content: "Hello" }]);
  });

  it("maps max_tokens to max_output_tokens for OpenAI Responses", () => {
    const request = buildOpenAIResponsesRequest(
      {
        apiKey: "test",
        provider: "openai",
        model: "gpt-test",
        metadata: { request: { max_tokens: 123 } },
      },
      input(),
    );

    expect(request).toMatchObject({
      model: "gpt-test",
      max_output_tokens: 123,
      stream: true,
    });
    expect(request).not.toHaveProperty("max_tokens");
  });

  it("declares available tools in provider requests", () => {
    const chatRequest = buildOpenAIChatCompletionRequest(
      { apiKey: "test", provider: "openai", model: "gpt-test" },
      inputWithTools(),
    );
    expect(chatRequest.tools).toEqual([
      {
        type: "function",
        function: {
          name: "todo_create",
          description: "Create a todo",
          parameters: {
            type: "object",
            properties: { title: { type: "string" } },
            required: ["title"],
          },
        },
      },
    ]);

    const anthropicRequest = buildAnthropicMessagesRequest(
      { apiKey: "test", provider: "anthropic", model: "claude-test" },
      inputWithTools(),
    );
    expect(anthropicRequest.tools).toEqual([
      {
        name: "todo_create",
        description: "Create a todo",
        input_schema: {
          type: "object",
          properties: { title: { type: "string" } },
          required: ["title"],
        },
      },
    ]);
  });

  it("uses provider-safe tool names for dotted Aithru tool names", () => {
    const input = {
      ...inputWithTools(),
      tools: [
        {
          name: "workspace.list_files",
          description: "List files",
          input_schema: {},
        },
        ...inputWithTools().tools,
      ],
    } as any;

    const chatRequest = buildOpenAIChatCompletionRequest(
      { apiKey: "test", provider: "openai", model: "gpt-test" },
      input,
    );
    expect((chatRequest.tools as any[]).map((tool) => tool.function.name)).toEqual([
      "workspace_list_files",
      "todo_create",
    ]);

    const responsesRequest = buildOpenAIResponsesRequest(
      { apiKey: "test", provider: "openai", model: "gpt-test" },
      input,
    );
    expect((responsesRequest.tools as any[]).map((tool) => tool.name)).toEqual([
      "workspace_list_files",
      "todo_create",
    ]);
  });

  it("maps provider-safe tool call names back to Aithru tool names", async () => {
    async function* chunks() {
      yield {
        choices: [
          {
            delta: {
              tool_calls: [
                {
                  index: 0,
                  id: "call_1",
                  function: {
                    name: "todo_create",
                    arguments: '{"title":"Ship it"}',
                  },
                },
              ],
            },
          },
        ],
      };
    }

    const adapter = new OpenAISdkModelAdapter({
      apiKey: "test",
      provider: "openai",
      model: "gpt-test",
    }) as any;

    const events = await collectModelEvents(
      adapter.createChatCompletionTurn(
        { chat: { completions: { create: () => chunks() } } },
        inputWithTools(),
      ),
    );

    expect(events).toContainEqual({
      type: "tool_call",
      id: "call_1",
      name: "todo.create",
      input: { title: "Ship it" },
    });
  });

  it("replays recent tool results as native OpenAI chat transcript", () => {
    const request = buildOpenAIChatCompletionRequest(
      { apiKey: "test", provider: "openai", model: "gpt-test" },
      {
        ...inputWithTools(),
        toolResults: [
          {
            id: "call_1",
            name: "todo.create",
            input: { title: "Ship it" },
            output: { id: "todo_1", title: "Ship it" },
          },
        ],
      },
    );

    const messages = request.messages as unknown[];
    expect(messages.slice(-2)).toEqual([
      {
        role: "assistant",
        content: null,
        tool_calls: [
          {
            id: "call_1",
            type: "function",
            function: {
              name: "todo_create",
              arguments: JSON.stringify({ title: "Ship it" }),
            },
          },
        ],
      },
      {
        role: "tool",
        tool_call_id: "call_1",
        content: JSON.stringify({ id: "todo_1", title: "Ship it" }),
      },
    ]);
  });

  it("fails clearly instead of faking native tool transcript replay", () => {
    expect(() =>
      buildOpenAIChatCompletionRequest(
        {
          apiKey: "test",
          provider: "custom",
          model: "thinking-tool-model",
          metadata: {
            compat: "qwen",
            request: {
              tools: [
                {
                  type: "function",
                  function: {
                    name: "todo.create",
                    description: "Create a todo",
                    parameters: { type: "object", properties: {} },
                  },
                },
              ],
            },
            when_thinking_enabled: { extra_body: { thinking: { type: "enabled" } } },
          },
        },
        {
          ...input("high"),
          toolResults: [
            { id: "call_1", name: "todo.create", output: { ok: true } },
          ],
        },
      ),
    ).toThrow(/NATIVE_TOOL_TRANSCRIPT_REQUIRED/);
  });
});
