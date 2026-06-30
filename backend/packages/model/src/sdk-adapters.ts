import Anthropic from "@anthropic-ai/sdk";
import type { AgentMessage } from "@aithru-agent/contracts";
import OpenAI from "openai";
import type {
  AgentModelAdapter,
  AgentModelTool,
  AgentModelToolResult,
  AgentModelTurnInput,
  ModelTurnEvent,
} from "./types.js";

export type ModelApiKind =
  | "openai_chat_completions"
  | "openai_responses"
  | "anthropic_messages";

export type ModelCompat = "deepseek" | "qwen" | "minimax" | "gemini_openai_compatible";

export interface SdkModelMetadata {
  api_kind?: ModelApiKind;
  base_url?: string;
  baseURL?: string;
  request?: Record<string, unknown>;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
  when_thinking_enabled?: Record<string, unknown>;
  thinking?: Record<string, unknown>;
  compat?: ModelCompat;
  use_responses_api?: boolean;
}

export interface SdkModelAdapterOptions {
  provider?: string;
  model: string;
  apiKey: string;
  capabilities?: {
    thinking?: boolean;
    vision?: boolean;
  } | null;
  metadata?: SdkModelMetadata | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function copyRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? structuredClone(value) : {};
}

function mergeRecord(
  base: Record<string, unknown>,
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const merged = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    merged[key] =
      isRecord(merged[key]) && isRecord(value)
        ? mergeRecord(merged[key] as Record<string, unknown>, value)
        : structuredClone(value);
  }
  return merged;
}

function providerModelName(model: string): string {
  return model.startsWith("custom:") ? model.slice("custom:".length).trim() : model;
}

function harnessOptions(input: AgentModelTurnInput): Record<string, unknown> {
  return isRecord(input.run.harness_options) ? input.run.harness_options : {};
}

function reasoningEffort(input: AgentModelTurnInput): string | null {
  const effort = harnessOptions(input).model_reasoning_effort;
  return typeof effort === "string" ? effort : null;
}

function thinkingEnabled(input: AgentModelTurnInput): boolean {
  const effort = reasoningEffort(input);
  return effort != null && effort !== "none";
}

function apiRole(role: AgentMessage["role"]): "system" | "user" | "assistant" | "tool" {
  return role === "system" || role === "assistant" || role === "tool" ? role : "user";
}

function inputMessages(input: AgentModelTurnInput) {
  const messages = input.messages.map((message) => ({
    role: apiRole(message.role),
    content: message.content,
  }));
  if (!input.messages.some((message) => message.run_id === input.run.id && message.role === "user")) {
    messages.push({ role: "user" as const, content: input.run.task_msg });
  }
  return messages;
}

function openAIBaseMessages(input: AgentModelTurnInput) {
  const instructions = harnessOptions(input).instructions;
  const messages = inputMessages(input);
  return typeof instructions === "string" && instructions.trim()
    ? [{ role: "system" as const, content: instructions.trim() }, ...messages]
    : messages;
}

function openAIChatMessages(input: AgentModelTurnInput) {
  return [...openAIBaseMessages(input), ...openAIChatToolTranscript(input)];
}

function openAIResponsesInput(input: AgentModelTurnInput) {
  return [...openAIBaseMessages(input), ...openAIResponsesToolTranscript(input)];
}

function anthropicMessages(input: AgentModelTurnInput) {
  const messages = inputMessages(input)
    .filter((message) => message.role !== "system")
    .map((message) => ({
      role: message.role === "assistant" ? "assistant" : "user",
      content: message.content,
    }));
  return [...messages, ...anthropicToolTranscript(input)];
}

function anthropicSystem(input: AgentModelTurnInput): string | undefined {
  const parts: string[] = [];
  const instructions = harnessOptions(input).instructions;
  if (typeof instructions === "string" && instructions.trim()) parts.push(instructions.trim());
  for (const message of input.messages) {
    if (message.role === "system" && message.content.trim()) parts.push(message.content.trim());
  }
  return parts.length ? parts.join("\n\n") : undefined;
}

function effectiveThinkingSettings(metadata: SdkModelMetadata): Record<string, unknown> {
  let settings = copyRecord(metadata.when_thinking_enabled);
  if (isRecord(metadata.thinking)) {
    settings = mergeRecord(settings, {
      thinking: mergeRecord(copyRecord(settings.thinking), metadata.thinking),
    });
  }
  return settings;
}

function applyThinkingRequest(
  request: Record<string, unknown>,
  metadata: SdkModelMetadata,
  input: AgentModelTurnInput,
): Record<string, unknown> {
  const settings = effectiveThinkingSettings(metadata);
  const hasThinkingSettings =
    Object.keys(settings).length > 0 || isRecord(metadata.thinking);
  const effort = reasoningEffort(input);
  let next = request;

  if (thinkingEnabled(input) && hasThinkingSettings) {
    if (metadata.supports_thinking === false) {
      throw new Error("Model profile does not support thinking");
    }
    next = mergeRecord(next, settings);
  }

  if (!thinkingEnabled(input) && hasThinkingSettings) {
    const extraBody = isRecord(settings.extra_body) ? settings.extra_body : {};
    const extraThinking = isRecord(extraBody.thinking) ? extraBody.thinking : {};
    const directThinking = isRecord(settings.thinking) ? settings.thinking : {};
    if (typeof extraThinking.type === "string") {
      next = mergeRecord(next, { extra_body: { thinking: { type: "disabled" } } });
      if (metadata.supports_reasoning_effort === true) next.reasoning_effort = "minimal";
    } else if (typeof directThinking.type === "string") {
      next = mergeRecord(next, { thinking: { type: "disabled" } });
    }
  }

  if (effort && effort !== "none" && metadata.supports_reasoning_effort === true) {
    next.reasoning_effort = effort;
  }
  if (metadata.supports_reasoning_effort !== true) delete next.reasoning_effort;
  return next;
}

function applyCompat(
  request: Record<string, unknown>,
  metadata: SdkModelMetadata,
): Record<string, unknown> {
  if (metadata.compat === "qwen") {
    const extraBody = copyRecord(request.extra_body);
    const thinking = isRecord(extraBody.thinking) ? extraBody.thinking : null;
    if (thinking?.type === "enabled" || thinking?.type === "disabled") {
      const chatTemplate = copyRecord(extraBody.chat_template_kwargs);
      chatTemplate.enable_thinking = thinking.type === "enabled";
      delete extraBody.thinking;
      extraBody.chat_template_kwargs = chatTemplate;
      request.extra_body = extraBody;
    }
  }
  if (metadata.compat === "minimax") {
    request.extra_body = mergeRecord(copyRecord(request.extra_body), {
      reasoning_split: true,
    });
  }
  return request;
}

function baseRequest(metadata: SdkModelMetadata, input: AgentModelTurnInput): Record<string, unknown> {
  const request = copyRecord(metadata.request);
  return applyCompat(applyThinkingRequest(request, metadata, input), metadata);
}

function withStreamUsage(request: Record<string, unknown>): Record<string, unknown> {
  return {
    ...request,
    stream_options: {
      include_usage: true,
      ...(isRecord(request.stream_options) ? request.stream_options : {}),
    },
  };
}

function requestDeclaresTools(request: Record<string, unknown>): boolean {
  return Array.isArray(request.tools) && request.tools.length > 0;
}

function inputDeclaresTools(input: AgentModelTurnInput): boolean {
  return availableTools(input).length > 0;
}

function availableTools(input: AgentModelTurnInput): AgentModelTool[] {
  return Array.isArray(input.tools) ? input.tools : [];
}

function replayableToolResults(input: AgentModelTurnInput): boolean {
  return input.toolResults.every((result) => isRecord(result.input));
}

function assertNoFakeNativeToolReplay(
  request: Record<string, unknown>,
  input: AgentModelTurnInput,
): void {
  if (
    input.toolResults.length > 0 &&
    (requestDeclaresTools(request) || inputDeclaresTools(input)) &&
    !replayableToolResults(input)
  ) {
    throw new Error(
      "NATIVE_TOOL_TRANSCRIPT_REQUIRED: provider-native tool calls need exact assistant/tool transcript replay",
    );
  }
}

function normalizedSchema(schema: Record<string, unknown>): Record<string, unknown> {
  return Object.keys(schema).length ? schema : { type: "object", properties: {} };
}

function providerToolName(name: string): string {
  return name.replace(/[^a-zA-Z0-9_-]/g, "_");
}

function aithruToolName(input: AgentModelTurnInput, name: string): string {
  return availableTools(input).find((tool) => providerToolName(tool.name) === name)?.name ?? name;
}

function openAIChatTools(tools: AgentModelTool[]) {
  return tools.map((tool) => ({
    type: "function" as const,
    function: {
      name: providerToolName(tool.name),
      description: tool.description,
      parameters: normalizedSchema(tool.input_schema),
    },
  }));
}

function openAIResponsesTools(tools: AgentModelTool[]) {
  return tools.map((tool) => ({
    type: "function" as const,
    name: providerToolName(tool.name),
    description: tool.description,
    parameters: normalizedSchema(tool.input_schema),
    strict: false,
  }));
}

function anthropicTools(tools: AgentModelTool[]) {
  return tools.map((tool) => ({
    name: providerToolName(tool.name),
    description: tool.description,
    input_schema: normalizedSchema(tool.input_schema),
  }));
}

function withTools(
  request: Record<string, unknown>,
  tools: unknown[],
): Record<string, unknown> {
  return tools.length ? { ...request, tools } : request;
}

function jsonText(value: unknown): string {
  return JSON.stringify(value ?? null) ?? "null";
}

function toolResultOutput(result: AgentModelToolResult): unknown {
  return result.error ? { error: result.error } : result.output;
}

function openAIChatToolTranscript(input: AgentModelTurnInput) {
  if (!input.toolResults.length || !replayableToolResults(input)) return [];
  return [
    {
      role: "assistant" as const,
      content: null,
      tool_calls: input.toolResults.map((result) => ({
        id: result.id,
        type: "function" as const,
        function: {
          name: providerToolName(result.name),
          arguments: jsonText(result.input),
        },
      })),
    },
    ...input.toolResults.map((result) => ({
      role: "tool" as const,
      tool_call_id: result.id,
      content: jsonText(toolResultOutput(result)),
    })),
  ];
}

function openAIResponsesToolTranscript(input: AgentModelTurnInput) {
  if (!input.toolResults.length || !replayableToolResults(input)) return [];
  return input.toolResults.flatMap((result) => [
    {
      type: "function_call" as const,
      call_id: result.id,
      name: providerToolName(result.name),
      arguments: jsonText(result.input),
    },
    {
      type: "function_call_output" as const,
      call_id: result.id,
      output: jsonText(toolResultOutput(result)),
    },
  ]);
}

function anthropicToolTranscript(input: AgentModelTurnInput) {
  if (!input.toolResults.length || !replayableToolResults(input)) return [];
  return [
    {
      role: "assistant" as const,
      content: input.toolResults.map((result) => ({
        type: "tool_use" as const,
        id: result.id,
        name: providerToolName(result.name),
        input: result.input ?? {},
      })),
    },
    {
      role: "user" as const,
      content: input.toolResults.map((result) => ({
        type: "tool_result" as const,
        tool_use_id: result.id,
        content: jsonText(toolResultOutput(result)),
        ...(result.error ? { is_error: true } : {}),
      })),
    },
  ];
}

export function resolveModelApiKind(
  provider?: string,
  metadata: SdkModelMetadata | null = null,
): ModelApiKind {
  if (metadata?.api_kind) return metadata.api_kind;
  if (provider === "anthropic") return "anthropic_messages";
  if (metadata?.use_responses_api === true) return "openai_responses";
  return "openai_chat_completions";
}

function requestMetadata(options: SdkModelAdapterOptions): SdkModelMetadata {
  const metadata = copyRecord(options.metadata) as SdkModelMetadata;
  const kind = resolveModelApiKind(options.provider, metadata);
  if (
    options.capabilities?.thinking === true &&
    kind !== "anthropic_messages" &&
    !isRecord(metadata.when_thinking_enabled) &&
    !isRecord(metadata.thinking)
  ) {
    metadata.supports_thinking ??= true;
    metadata.when_thinking_enabled = {
      extra_body: { thinking: { type: "enabled" } },
    };
  }
  return metadata;
}

export function buildOpenAIChatCompletionRequest(
  options: SdkModelAdapterOptions,
  input: AgentModelTurnInput,
): Record<string, unknown> {
  const metadata = requestMetadata(options);
  const request = withStreamUsage(
    withTools(baseRequest(metadata, input), openAIChatTools(availableTools(input))),
  );
  assertNoFakeNativeToolReplay(request, input);
  return {
    ...request,
    model: providerModelName(options.model),
    messages: openAIChatMessages(input),
    stream: true,
  };
}

export function buildOpenAIResponsesRequest(
  options: SdkModelAdapterOptions,
  input: AgentModelTurnInput,
): Record<string, unknown> {
  const metadata = requestMetadata(options);
  const request = withTools(
    baseRequest(metadata, input),
    openAIResponsesTools(availableTools(input)),
  );
  assertNoFakeNativeToolReplay(request, input);
  if (request.max_tokens != null && request.max_output_tokens == null) {
    request.max_output_tokens = request.max_tokens;
    delete request.max_tokens;
  }
  return {
    ...request,
    model: providerModelName(options.model),
    input: openAIResponsesInput(input),
    stream: true,
  };
}

export function buildAnthropicMessagesRequest(
  options: SdkModelAdapterOptions,
  input: AgentModelTurnInput,
): Record<string, unknown> {
  const request = withTools(
    baseRequest(requestMetadata(options), input),
    anthropicTools(availableTools(input)),
  );
  assertNoFakeNativeToolReplay(request, input);
  const system = anthropicSystem(input);
  return {
    ...request,
    model: providerModelName(options.model),
    messages: anthropicMessages(input),
    max_tokens: request.max_tokens ?? 4096,
    ...(system ? { system } : {}),
    stream: true,
  };
}

function parseToolInput(value: unknown): Record<string, unknown> {
  if (value == null) return {};
  if (typeof value === "string") {
    const parsed = JSON.parse(value);
    return isRecord(parsed) ? parsed : {};
  }
  return isRecord(value) ? value : {};
}

function errorEvent(error: unknown): ModelTurnEvent {
  const err = error as any;
  const status = Number(err?.status ?? err?.code);
  return {
    type: "failed",
    error: {
      code: String(err?.code ?? err?.name ?? "MODEL_REQUEST_FAILED"),
      message: String(err?.message ?? "Model request failed"),
      retryable: Number.isFinite(status) ? status >= 500 : false,
    },
  };
}

function openAIClient(options: SdkModelAdapterOptions): OpenAI {
  const baseURL = options.metadata?.base_url ?? options.metadata?.baseURL;
  return new OpenAI({
    apiKey: options.apiKey,
    ...(baseURL ? { baseURL } : {}),
  });
}

function anthropicClient(options: SdkModelAdapterOptions): Anthropic {
  const baseURL = options.metadata?.base_url ?? options.metadata?.baseURL;
  return new Anthropic({
    apiKey: options.apiKey,
    ...(baseURL ? { baseURL } : {}),
  });
}

function textAndReasoningFromChatMessage(message: any, compat?: ModelCompat) {
  let content = typeof message?.content === "string" ? message.content : "";
  let reasoning =
    typeof message?.reasoning_content === "string"
      ? message.reasoning_content
      : typeof message?.reasoning === "string"
        ? message.reasoning
        : "";
  if (compat === "minimax") {
    const match = content.match(/<think>\s*([\s\S]*?)\s*<\/think>/);
    if (match) {
      reasoning = reasoning ? `${reasoning}\n\n${match[1].trim()}` : match[1].trim();
      content = content.replace(match[0], "").trim();
    }
  }
  return { content, reasoning };
}

export class OpenAISdkModelAdapter implements AgentModelAdapter {
  constructor(private options: SdkModelAdapterOptions) {}

  async *createTurn(input: AgentModelTurnInput): AsyncIterable<ModelTurnEvent> {
    try {
      const kind = resolveModelApiKind(this.options.provider, this.options.metadata ?? null);
      const client = openAIClient(this.options);
      if (kind === "openai_responses") {
        yield* this.createResponsesTurn(client, input);
      } else {
        yield* this.createChatCompletionTurn(client, input);
      }
    } catch (error) {
      yield errorEvent(error);
    }
  }

  private async *createChatCompletionTurn(
    client: OpenAI,
    input: AgentModelTurnInput,
  ): AsyncIterable<ModelTurnEvent> {
    const stream = await client.chat.completions.create(
      buildOpenAIChatCompletionRequest(this.options, input) as any,
    );
    let content = "";
    const toolCalls = new Map<
      number,
      { id: string; name: string; arguments: string }
    >();
    for await (const chunk of stream as any) {
      if (chunk?.usage) {
        yield {
          type: "usage",
          inputTokens: Number(chunk.usage.prompt_tokens ?? 0),
          outputTokens: Number(chunk.usage.completion_tokens ?? 0),
          totalTokens:
            chunk.usage.total_tokens == null
              ? undefined
              : Number(chunk.usage.total_tokens),
        };
      }
      for (const choice of chunk?.choices ?? []) {
        const delta = choice.delta ?? {};
        const reasoning = String(delta.reasoning_content ?? delta.reasoning ?? "");
        if (reasoning) yield { type: "reasoning_delta", delta: reasoning };
        if (typeof delta.content === "string" && delta.content) {
          content += delta.content;
          yield { type: "text_delta", delta: delta.content };
        }
        for (const toolCall of delta.tool_calls ?? []) {
          const index = Number(toolCall.index ?? 0);
          const current = toolCalls.get(index) ?? { id: "", name: "", arguments: "" };
          toolCalls.set(index, {
            id: String(toolCall.id ?? current.id),
            name: String(toolCall.function?.name ?? current.name),
            arguments: `${current.arguments}${toolCall.function?.arguments ?? ""}`,
          });
        }
      }
    }
    for (const toolCall of toolCalls.values()) {
      if (!toolCall.name) continue;
      yield {
        type: "tool_call",
        id: toolCall.id || toolCall.name,
        name: aithruToolName(input, toolCall.name),
        input: parseToolInput(toolCall.arguments),
      };
    }
    yield { type: "completed", content };
  }

  private async *createResponsesTurn(
    client: OpenAI,
    input: AgentModelTurnInput,
  ): AsyncIterable<ModelTurnEvent> {
    const stream = await client.responses.create(
      buildOpenAIResponsesRequest(this.options, input) as any,
    );
    let content = "";
    const toolCalls = new Map<string, { id: string; name: string; arguments: string }>();
    for await (const event of stream as any) {
      if (event.type === "response.output_text.delta") {
        content += String(event.delta ?? "");
        yield { type: "text_delta", delta: String(event.delta ?? "") };
      } else if (
        event.type === "response.reasoning_text.delta" ||
        event.type === "response.reasoning_summary_text.delta"
      ) {
        yield { type: "reasoning_delta", delta: String(event.delta ?? "") };
      } else if (event.type === "response.function_call_arguments.done") {
        toolCalls.set(String(event.item_id), {
          id: String(event.item_id),
          name: String(event.name),
          arguments: String(event.arguments ?? ""),
        });
      } else if (
        event.type === "response.output_item.done" &&
        event.item?.type === "function_call"
      ) {
        toolCalls.set(String(event.item.id ?? event.item.call_id), {
          id: String(event.item.call_id ?? event.item.id),
          name: String(event.item.name),
          arguments: String(event.item.arguments ?? ""),
        });
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
      } else if (event.type === "response.failed" || event.type === "response.error") {
        yield {
          type: "failed",
          error: {
            code: String(event.error?.code ?? "MODEL_REQUEST_FAILED"),
            message: String(event.error?.message ?? "Model request failed"),
            retryable: false,
          },
        };
        return;
      }
    }
    for (const toolCall of toolCalls.values()) {
      if (!toolCall.name) continue;
      yield {
        type: "tool_call",
        id: toolCall.id,
        name: aithruToolName(input, toolCall.name),
        input: parseToolInput(toolCall.arguments),
      };
    }
    yield { type: "completed", content };
  }
}

export class AnthropicSdkModelAdapter implements AgentModelAdapter {
  constructor(private options: SdkModelAdapterOptions) {}

  async *createTurn(input: AgentModelTurnInput): AsyncIterable<ModelTurnEvent> {
    try {
      const stream = anthropicClient(this.options).messages.stream(
        buildAnthropicMessagesRequest(this.options, input) as any,
      );
      let content = "";
      for await (const event of stream as any) {
        if (event.type === "content_block_delta" && event.delta?.type === "text_delta") {
          const delta = String(event.delta.text ?? "");
          content += delta;
          yield { type: "text_delta", delta };
        } else if (
          event.type === "content_block_delta" &&
          event.delta?.type === "thinking_delta"
        ) {
          yield { type: "reasoning_delta", delta: String(event.delta.thinking ?? "") };
        }
      }
      const finalMessage = await stream.finalMessage();
      for (const block of (finalMessage as any).content ?? []) {
        if (block?.type === "tool_use") {
          yield {
            type: "tool_call",
            id: String(block.id),
            name: aithruToolName(input, String(block.name)),
            input: parseToolInput(block.input),
          };
        }
      }
      const usage = (finalMessage as any).usage;
      if (usage) {
        yield {
          type: "usage",
          inputTokens: Number(usage.input_tokens ?? 0),
          outputTokens: Number(usage.output_tokens ?? 0),
          totalTokens:
            usage.total_tokens == null ? undefined : Number(usage.total_tokens),
        };
      }
      yield { type: "completed", content };
    } catch (error) {
      yield errorEvent(error);
    }
  }
}

export function createSdkModelAdapter(options: SdkModelAdapterOptions): AgentModelAdapter {
  return resolveModelApiKind(options.provider, options.metadata ?? null) === "anthropic_messages"
    ? new AnthropicSdkModelAdapter(options)
    : new OpenAISdkModelAdapter(options);
}
