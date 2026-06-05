import type { AgentModelEvent, AgentModelInput } from "@aithru/agent-core";
import { afterEach, describe, expect, test, vi } from "vitest";
import { OpenAICompatibleAgentModelAdapter } from "./index.js";

const modelInput: AgentModelInput = {
  task: {
    id: "task_openai_compatible_test",
    goal: "Summarize repository state.",
  },
  mode: "classify",
};

function jsonResponse(body: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    ...init,
  });
}

async function collectEvents(input = modelInput) {
  const model = new OpenAICompatibleAgentModelAdapter({
    baseUrl: "https://provider.test/v1",
    model: "test-model",
  });
  const events: AgentModelEvent[] = [];

  for await (const event of model.generate(input)) {
    events.push(event);
  }

  return events;
}

function stubFetch(response: Response) {
  const fetchMock = vi.fn<typeof fetch>();
  fetchMock.mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("OpenAICompatibleAgentModelAdapter", () => {
  test("sends a POST request to the chat completions endpoint", async () => {
    const fetchMock = stubFetch(
      jsonResponse({ choices: [{ message: { content: "complete" } }] }),
    );

    await collectEvents();

    expect(fetchMock).toHaveBeenCalledWith(
      "https://provider.test/v1/chat/completions",
      expect.objectContaining({ method: "POST" }),
    );
  });

  test("sends an Authorization header when apiKey is provided", async () => {
    const fetchMock = stubFetch(
      jsonResponse({ choices: [{ message: { content: "complete" } }] }),
    );
    const model = new OpenAICompatibleAgentModelAdapter({
      baseUrl: "https://provider.test/v1",
      apiKey: "secret-token",
      model: "test-model",
    });

    for await (const _event of model.generate(modelInput)) {
      // consume events
    }

    const request = fetchMock.mock.calls[0]?.[1] as { headers?: Record<string, string> };
    expect(request.headers).toMatchObject({
      Authorization: "Bearer secret-token",
    });
  });

  test("handles a trailing slash in baseUrl", async () => {
    const fetchMock = stubFetch(
      jsonResponse({ choices: [{ message: { content: "complete" } }] }),
    );
    const model = new OpenAICompatibleAgentModelAdapter({
      baseUrl: "https://provider.test/v1/",
      model: "test-model",
    });

    for await (const _event of model.generate(modelInput)) {
      // consume events
    }

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "https://provider.test/v1/chat/completions",
    );
  });

  test("includes task goal, input, mode, step, tools, and output schema in messages when provided", async () => {
    const fetchMock = stubFetch(
      jsonResponse({ choices: [{ message: { content: "complete" } }] }),
    );
    const input: AgentModelInput = {
      task: {
        id: "task_prompt",
        goal: "Classify the request.",
        input: { text: "Please research this repository." },
      },
      mode: "execute",
      step: {
        id: "step_read",
        title: "Read repository",
        objective: "Inspect README and package manifests.",
        allowedTools: ["repo.read"],
      },
      tools: [
        {
          name: "repo.read",
          description: "Read a file from the repository.",
          inputSchema: { type: "object", properties: { path: { type: "string" } } },
        },
      ],
      outputSchema: {
        type: "object",
        properties: { summary: { type: "string" } },
      },
    };
    const model = new OpenAICompatibleAgentModelAdapter({
      baseUrl: "https://provider.test/v1",
      defaultSystemPrompt: "You are a careful agent.",
      model: "test-model",
    });

    for await (const _event of model.generate(input)) {
      // consume events
    }

    const request = fetchMock.mock.calls[0]?.[1] as { body?: string };
    const body = JSON.parse(request.body ?? "{}") as {
      messages: Array<{ role: string; content: string }>;
    };

    expect(body.messages[0]).toEqual({
      role: "system",
      content: "You are a careful agent.",
    });
    expect(body.messages[1]?.role).toBe("user");
    expect(body.messages[1]?.content).toContain("Task goal:\nClassify the request.");
    expect(body.messages[1]?.content).toContain('"text": "Please research this repository."');
    expect(body.messages[1]?.content).toContain("Mode:\nexecute");
    expect(body.messages[1]?.content).toContain(
      "Step objective:\nInspect README and package manifests.",
    );
    expect(body.messages[1]?.content).toContain('"name": "repo.read"');
    expect(body.messages[1]?.content).toContain('"summary"');
  });

  test("parses plain JSON into a structured output event", async () => {
    stubFetch(jsonResponse({ choices: [{ message: { content: '{"route":"research"}' } }] }));

    await expect(collectEvents()).resolves.toEqual([
      { type: "structured.output", value: { route: "research" } },
    ]);
  });

  test("parses a final event envelope", async () => {
    stubFetch(
      jsonResponse({
        choices: [{ message: { content: '{"type":"final","output":"complete"}' } }],
      }),
    );

    await expect(collectEvents()).resolves.toEqual([
      { type: "final", output: "complete" },
    ]);
  });

  test("parses an events array into multiple events", async () => {
    stubFetch(
      jsonResponse({
        choices: [
          {
            message: {
              content: JSON.stringify({
                events: [
                  { type: "text.delta", text: "hello" },
                  { type: "structured.output", value: { route: "simple" } },
                  {
                    type: "tool_call.proposed",
                    toolCall: {
                      id: "call_read",
                      toolName: "repo.read",
                      arguments: { path: "README.md" },
                    },
                  },
                  { type: "final", output: "complete" },
                ],
              }),
            },
          },
        ],
      }),
    );

    await expect(collectEvents()).resolves.toEqual([
      { type: "text.delta", text: "hello" },
      { type: "structured.output", value: { route: "simple" } },
      {
        type: "tool_call.proposed",
        toolCall: {
          id: "call_read",
          toolName: "repo.read",
          arguments: { path: "README.md" },
        },
      },
      { type: "final", output: "complete" },
    ]);
  });

  test("returns non-JSON model content as a final event", async () => {
    stubFetch(jsonResponse({ choices: [{ message: { content: "plain completion" } }] }));

    await expect(collectEvents()).resolves.toEqual([
      { type: "final", output: "plain completion" },
    ]);
  });

  test("yields error events for malformed event envelopes", async () => {
    stubFetch(
      jsonResponse({
        choices: [
          {
            message: {
              content: JSON.stringify({
                events: [
                  { type: "unknown.event", value: "bad" },
                  { type: "tool_call.proposed" },
                ],
              }),
            },
          },
        ],
      }),
    );

    await expect(collectEvents()).resolves.toEqual([
      {
        type: "error",
        error: {
          code: "invalid_model_event",
          message: expect.stringContaining("Unknown model event type"),
        },
      },
      {
        type: "error",
        error: {
          code: "invalid_model_event",
          message: expect.stringContaining("tool_call.proposed"),
        },
      },
    ]);
  });

  test("throws a clear error on non-2xx responses", async () => {
    stubFetch(
      new Response("provider unavailable with a detailed body", {
        status: 503,
        statusText: "Service Unavailable",
      }),
    );

    await expect(collectEvents()).rejects.toThrow(
      /OpenAI-compatible request failed with status 503 Service Unavailable: provider unavailable/,
    );
  });

  test("throws a clear error when response shape has no message content", async () => {
    stubFetch(jsonResponse({ choices: [{ message: {} }] }));

    await expect(collectEvents()).rejects.toThrow(
      "OpenAI-compatible response did not include choices[0].message.content",
    );
  });

  test("aborts on timeout", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    const fetchMock = vi.fn<typeof fetch>((_url, init) => {
      signal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener("abort", () => {
          reject(new Error("request aborted"));
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const model = new OpenAICompatibleAgentModelAdapter({
      baseUrl: "https://provider.test/v1",
      model: "test-model",
      timeoutMs: 10,
    });

    const promise = expect(collectEventsForModel(model)).rejects.toThrow(
      "request aborted",
    );
    await vi.advanceTimersByTimeAsync(10);

    expect(signal?.aborted).toBe(true);
    await promise;
  });
});

async function collectEventsForModel(model: OpenAICompatibleAgentModelAdapter) {
  const events: AgentModelEvent[] = [];

  for await (const event of model.generate(modelInput)) {
    events.push(event);
  }

  return events;
}
