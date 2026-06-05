# @aithru/agent-model-openai-compatible

OpenAI-compatible HTTP model adapter for Aithru Agent.

This package implements `AgentModelAdapter` for providers that expose a
`/chat/completions` endpoint. It uses built-in `fetch` and does not depend on
the OpenAI SDK.

## Usage

```ts
import { OpenAICompatibleAgentModelAdapter } from "@aithru/agent-model-openai-compatible";

const model = new OpenAICompatibleAgentModelAdapter({
  baseUrl: "https://api.openai.com/v1",
  apiKey: process.env.OPENAI_API_KEY,
  model: "gpt-4.1-mini",
});
```

The adapter sends a non-streaming chat completion request and converts the
assistant message content into `AgentModelEvent` values.

## Tool Boundary

This adapter does not execute tools.

It may emit a `tool_call.proposed` model event when the model returns a valid
event envelope, but tool execution remains the responsibility of `AgentRuntime`
through `AgentHost.callTool`.

## Compatible Providers

Use this adapter with OpenAI-compatible providers such as:

- OpenAI
- DeepSeek
- Qwen-compatible endpoints
- local vLLM-style endpoints
- internal OpenAI-compatible gateways

## Model Output

For V0, model content is parsed with a small event envelope:

- `{ "type": "final", "output": "..." }`
- `{ "type": "structured.output", "value": { ... } }`
- `{ "type": "tool_call.proposed", "toolCall": { ... } }`
- `{ "events": [{ "type": "text.delta", "text": "..." }] }`

Plain JSON without an event envelope becomes `structured.output`.
Non-JSON text becomes `final`.
