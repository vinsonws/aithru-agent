import { describe, expect, it } from "vitest";
import type { AgentRun } from "@aithru-agent/contracts";
import { runTerminalProcessors } from "@aithru-agent/harness";
import { TestModelAdapter } from "@aithru-agent/model";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";

function createRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run_terminal_processors",
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: "thread_terminal_processors",
    workspace_id: "ws_terminal_processors",
    task_msg: "Summarize the conversation",
    scopes: ["*"],
    harness_options: null,
    status: "completed",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: "2026-01-01T00:01:00Z",
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
    ...overrides,
  };
}

function createThread(store: InMemoryStore, threadId: string, title = "Thread") {
  store.createThread({
    id: threadId,
    org_id: "org_1",
    owner_user_id: "user_1",
    title,
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  });
}

function createMessages(store: InMemoryStore, threadId: string, count: number) {
  for (let i = 0; i < count; i += 1) {
    store.createMessage({
      id: `msg_${i}`,
      thread_id: threadId,
      role: i % 2 === 0 ? "user" : "assistant",
      content: `Message ${i}`,
      run_id: "run_terminal_processors",
      workspace_paths: [],
      created_at: `2026-01-01T00:00:${String(i).padStart(2, "0")}Z`,
    });
  }
}

describe("terminal processors", () => {
  it("uses the lightweight model to summarize dropped context", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const threadId = "thread_summary_model";
    createThread(store, threadId);
    createMessages(store, threadId, 13);
    const run = store.createRun(createRun({ thread_id: threadId }));

    const modelAdapter = new TestModelAdapter([
      (input) => {
        expect(input.context.purpose).toBe("context_summary");
        expect(input.run.task_msg).toContain("Previous summary");
        expect(input.run.task_msg).toContain("Message 0");
        expect(input.run.task_msg).not.toContain("Message 12");
        expect(input.run.harness_options).toMatchObject({
          instructions: expect.stringContaining("Return only the updated summary"),
          model_reasoning_effort: "none",
        });
        return [
          { type: "text_delta", delta: "Concise summary." },
          { type: "completed" },
        ];
      },
    ]);

    await runTerminalProcessors({
      store,
      eventWriter,
      run,
      titleModelAdapter: modelAdapter,
    });

    expect(store.getLatestContextSummary(threadId)?.summary).toBe("Concise summary.");
    expect(store.listEvents(run.id).some((event) => event.type === EVENT_TYPES.CONTEXT_SUMMARY_CREATED)).toBe(true);
  });

  it("builds each new summary on the prior summary", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const threadId = "thread_summary_progressive";
    createThread(store, threadId);
    createMessages(store, threadId, 15);
    store.createContextSummary({
      id: "summary_prior",
      org_id: "org_1",
      thread_id: threadId,
      run_id: "run_prior",
      summary: "Earlier summary.",
      source_message_count: 2,
      created_at: "2026-01-01T00:10:00Z",
    });
    const run = store.createRun(createRun({ id: "run_progressive", thread_id: threadId }));

    const modelAdapter = new TestModelAdapter([
      (input) => {
        expect(input.context.purpose).toBe("context_summary");
        expect(input.run.task_msg).toContain("Previous summary:\nEarlier summary.");
        expect(input.run.task_msg).toContain("Message 2");
        expect(input.run.task_msg).not.toContain("Message 0");
        expect(input.run.task_msg).not.toContain("Message 1");
        return [
          { type: "text_delta", delta: "Updated summary." },
          { type: "completed" },
        ];
      },
    ]);

    await runTerminalProcessors({
      store,
      eventWriter,
      run,
      titleModelAdapter: modelAdapter,
    });

    const summaries = store.listContextSummaries(threadId);
    expect(summaries).toHaveLength(2);
    expect(summaries.at(-1)?.source_message_count).toBe(3);
    expect(summaries.at(-1)?.summary).toBe("Updated summary.");
  });

  it("falls back to the naive summary when the model fails", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const threadId = "thread_summary_fallback";
    createThread(store, threadId);
    createMessages(store, threadId, 13);
    const run = store.createRun(createRun({ id: "run_fallback", thread_id: threadId }));

    const modelAdapter = new TestModelAdapter([
      [
        {
          type: "failed",
          error: {
            code: "rate_limit_exceeded",
            message: "slow down",
            retryable: true,
          },
        },
      ],
    ]);

    await runTerminalProcessors({
      store,
      eventWriter,
      run,
      titleModelAdapter: modelAdapter,
    });

    expect(store.getLatestContextSummary(threadId)?.summary).toContain("Message 0");
    expect(store.listEvents(run.id).some((event) => event.type === EVENT_TYPES.CONTEXT_SUMMARY_CREATED)).toBe(true);
  });
});
