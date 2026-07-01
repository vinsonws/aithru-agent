import { describe, expect, it } from "vitest";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { ModelTurnLoop, runTerminalProcessors } from "@aithru-agent/harness";
import { TestModelAdapter } from "@aithru-agent/model";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";

function createRun(): AgentRun {
  return {
    id: "run_model",
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_model",
    task_msg: "Create a todo",
    scopes: ["*"],
    harness_options: null,
    status: "queued",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
  };
}

describe("ModelTurnLoop", () => {
  it("persists assistant replies for threaded runs", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    const threadId = "thread_model";
    store.createThread({
      id: threadId,
      org_id: "org_1",
      owner_user_id: "user_1",
      title: "Threaded model",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    store.createRun({ ...run, thread_id: threadId });
    store.createMessage({
      id: "msg_user",
      thread_id: threadId,
      role: "user",
      content: run.task_msg,
      run_id: run.id,
      workspace_paths: [],
      created_at: "2026-01-01T00:00:00Z",
    });

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          { type: "text_delta", delta: "Thread answer." },
          { type: "completed" },
        ],
      ]),
    });

    await loop.execute({ ...run, thread_id: threadId });

    const messages = store.listMessages(threadId);
    const assistantMessage = messages.find(
      (message) => message.role === "assistant" && message.content === "Thread answer.",
    );
    const messageCreated = store.listEvents(run.id).find((event) => event.type === "message.created")!;
    const messageCompleted = store.listEvents(run.id).find((event) => event.type === "message.completed")!;
    const createdPayload = messageCreated.payload as Record<string, unknown>;
    const completedPayload = messageCompleted.payload as Record<string, unknown>;

    expect(assistantMessage).toBeDefined();
    expect(completedPayload.message_id).toBe(createdPayload.message_id);
    expect(completedPayload.thread_message_id).toBe(assistantMessage!.id);
    expect(assistantMessage!.id).not.toBe(createdPayload.message_id);
    expect((store.getRun(run.id)?.result as Record<string, unknown> | null)?.thread_message_id).toBe(
      assistantMessage!.id,
    );
  });

  it("keeps stored messages complete while sending bounded context to the model", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    const threadId = "thread_context";
    const longContent = "x".repeat(1200);
    store.createThread({
      id: threadId,
      org_id: "org_1",
      owner_user_id: "user_1",
      title: "Context model",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    store.createRun({ ...run, thread_id: threadId });
    store.createMessage({
      id: "msg_long",
      thread_id: threadId,
      role: "user",
      content: longContent,
      run_id: run.id,
      workspace_paths: [],
      created_at: "2026-01-01T00:00:00Z",
    });

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        (input) => {
          expect(input.messages[0].content.length).toBeLessThan(longContent.length);
          return [{ type: "text_delta", delta: "ok" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute({ ...run, thread_id: threadId });

    expect(store.getMessage("msg_long")?.content).toBe(longContent);
    expect(store.listEvents(run.id).map((event) => event.type)).toContain("context.packet.built");
  });

  it("uses the model adapter to generate untitled thread titles", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    const threadId = "thread_title_model";
    store.createThread({
      id: threadId,
      org_id: "org_1",
      owner_user_id: "user_1",
      title: null,
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    store.createRun({ ...run, thread_id: threadId });
    store.createMessage({
      id: "msg_title_user",
      thread_id: threadId,
      role: "user",
      content: "Please help me plan next week's launch checklist",
      run_id: run.id,
      workspace_paths: [],
      created_at: "2026-01-01T00:00:00Z",
    });

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [{ type: "text_delta", delta: "Sure, here is a launch checklist." }, { type: "completed" }],
        (input) => {
          expect(input.context.purpose).toBe("thread_title");
          return [{ type: "text_delta", delta: "Launch Checklist" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute({ ...run, thread_id: threadId });

    expect(store.getThread(threadId)?.title).toBe("Launch Checklist");
  });

  it("routes model tool calls through the CapabilityRouter and records usage", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun(run);

    const modelAdapter = new TestModelAdapter([
      [
        { type: "text_delta", delta: "I will create a todo." },
        {
          type: "tool_call",
          id: "model_tc_1",
          name: "todo.create",
          input: { title: "From model" },
        },
        { type: "usage", inputTokens: 12, outputTokens: 8, totalTokens: 20 },
        { type: "completed" },
      ],
      (input) => [
        {
          type: "text_delta",
          delta: ` Tool result count: ${input.toolResults.length}. Done.`,
        },
        { type: "completed" },
      ],
    ]);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter,
    });

    const completed = await loop.execute(run);
    expect(completed.status).toBe("completed");
    expect(store.listTodos(run.id)[0].title).toBe("From model");

    const eventTypes = store.listEvents(run.id).map((event) => event.type);
    expect(eventTypes).toContain("model.usage");
    expect(store.listEvents(run.id).find((event) => event.type === "model.usage")?.payload).toEqual({
      requests: 1,
      input_tokens: 12,
      output_tokens: 8,
      total_tokens: 20,
    });
    expect(eventTypes).toContain("tool.proposed");
    expect(eventTypes).toContain("tool.completed");
    expect(eventTypes).toContain("run.completed");
  });

  it("allows multi-step skill runs beyond eight model turns by default", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun(run);

    const toolTurns = Array.from({ length: 12 }, (_, index) => [
      {
        type: "tool_call" as const,
        id: `model_tc_${index}`,
        name: "workspace.list_files",
        input: { path: `/file_${index}.txt` },
      },
      { type: "completed" as const },
    ]);
    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        ...toolTurns,
        [{ type: "text_delta", delta: "done" }, { type: "completed" }],
      ]),
    });

    const completed = await loop.execute(run);

    expect(completed.status).toBe("completed");
    expect(store.listEvents(run.id).filter((event) => event.type === "context.packet.built")).toHaveLength(13);
    expect(store.listEvents(run.id).filter((event) => event.type === "tool.completed")).toHaveLength(12);
  });

  it("forwards streamed tool input without executing or approving a tool", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun(run);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          {
            type: "tool_input_delta",
            inputStreamId: "chat:0",
            toolCallId: "call_1",
            index: 0,
            name: "workspace.write_file",
            delta: '{"path":"/draft.md"',
          },
          { type: "completed" },
        ],
        (input) => {
          expect(input.toolResults.length).toBe(1);
          return [{ type: "text_delta", delta: "done" }, { type: "completed" }];
        },
      ]),
    });

    const completed = await loop.execute(run);

    expect(completed.status).toBe("completed");
    expect(store.listApprovals({ run_id: run.id })).toEqual([]);
    expect(store.listWorkspaceFiles(run.workspace_id)).toEqual([]);
    expect(store.listEvents(run.id).map((event) => event.type)).toContain("tool.input_delta");
    expect(store.listEvents(run.id).map((event) => event.type)).not.toContain("tool.proposed");
    expect(store.listEvents(run.id).map((event) => event.type)).not.toContain("tool.started");
  });

  it("coalesces small streamed tool input deltas for the same stream", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun(run);

    const streamEvent = {
      type: "tool_input_delta" as const,
      inputStreamId: "chat:0",
      toolCallId: "call_1",
      index: 0,
      name: "workspace.write_file",
    };
    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          { ...streamEvent, delta: '{"path":' },
          { ...streamEvent, delta: '"/draft.html"' },
          { ...streamEvent, delta: ',"content":' },
          { ...streamEvent, delta: '"hello"}' },
          { type: "completed" },
        ],
      ]),
    });

    await loop.execute(run);

    const inputEvents = store.listEvents(run.id).filter((event) => event.type === "tool.input_delta");
    const payload = inputEvents[0]?.payload as Record<string, unknown>;

    expect(inputEvents).toHaveLength(1);
    expect(payload).toMatchObject({
      input_stream_id: "chat:0",
      tool_call_id: "call_1",
      index: 0,
      name: "workspace.write_file",
      input_delta: '{"path":"/draft.html","content":"hello"}',
    });
  });

  it("flushes coalesced streamed tool input before the final tool proposal", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun(run);

    const streamEvent = {
      type: "tool_input_delta" as const,
      inputStreamId: "chat:0",
      toolCallId: "model_tc_1",
      index: 0,
      name: "todo.create",
    };
    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          { ...streamEvent, delta: '{"title":' },
          { ...streamEvent, delta: '"From ' },
          { ...streamEvent, delta: 'stream"}' },
          {
            type: "tool_call",
            id: "model_tc_1",
            inputStreamId: "chat:0",
            name: "todo.create",
            input: { title: "From stream" },
          },
          { type: "completed" },
        ],
        [{ type: "text_delta", delta: "done" }, { type: "completed" }],
      ]),
    });

    await loop.execute(run);

    const events = store.listEvents(run.id);
    const inputEvents = events.filter((event) => event.type === "tool.input_delta");
    const inputIndex = events.findIndex((event) => event.type === "tool.input_delta");
    const proposedIndex = events.findIndex((event) => event.type === "tool.proposed");
    const payload = inputEvents[0]?.payload as Record<string, unknown>;

    expect(inputEvents).toHaveLength(1);
    expect(inputIndex).toBeGreaterThan(-1);
    expect(inputIndex).toBeLessThan(proposedIndex);
    expect(payload.input_delta).toBe('{"title":"From stream"}');
  });

  it("carries input stream ids into final tool proposal events", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun(run);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          {
            type: "tool_input_delta",
            inputStreamId: "chat:0",
            toolCallId: "model_tc_1",
            index: 0,
            name: "todo.create",
            delta: '{"title":"From stream"}',
          },
          {
            type: "tool_call",
            id: "model_tc_1",
            inputStreamId: "chat:0",
            name: "todo.create",
            input: { title: "From stream" },
          },
          { type: "completed" },
        ],
        (input) => {
          expect(input.toolResults.length).toBe(1);
          return [{ type: "text_delta", delta: "done" }, { type: "completed" }];
        },
      ]),
    });

    const completed = await loop.execute(run);
    const proposed = store
      .listEvents(run.id)
      .find((event) => event.type === "tool.proposed")!;

    expect(completed.status).toBe("completed");
    expect((proposed.payload as Record<string, unknown>).input_stream_id).toBe("chat:0");
  });

  it("offers basic tools in every composer strength and todo tools only in plan strengths", async () => {
    const basicTools = [
      "workspace.list_files",
      "workspace.read_file",
      "workspace.write_file",
      "workspace.patch_file",
      "workspace.delete_file",
      "ask_clarification",
      "presentation.present",
      "skill.load",
    ];

    for (const mode of ["flash", "thinking", "pro", "ultra"]) {
      const isPlanMode = mode === "pro" || mode === "ultra";
      const store = new InMemoryStore();
      const eventWriter = new AgentEventWriter(store);
      const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
      const run = {
        ...createRun(),
        id: `run_${mode}`,
        harness_options: {
          mode,
          is_plan_mode: mode === "pro" || mode === "ultra",
        } as any,
      };
      store.createRun(run);

      const loop = new ModelTurnLoop({
        store,
        eventWriter,
        capabilityRouter,
        modelAdapter: new TestModelAdapter([
          (input) => {
            expect(input.tools?.map((tool) => tool.name)).toEqual(
              isPlanMode
                ? [
                    "workspace.list_files",
                    "workspace.read_file",
                    "workspace.write_file",
                    "workspace.patch_file",
                    "workspace.delete_file",
                    "todo.create",
                    "todo.update",
                    "ask_clarification",
                    "presentation.present",
                    "skill.load",
                  ]
                : basicTools,
            );
            return [{ type: "text_delta", delta: "ok" }, { type: "completed" }];
          },
        ]),
      });

      await loop.execute(run);
    }
  });

  it("offers todo planning guidance only in plan mode", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun({
      ...run,
      harness_options: {
        mode: "pro",
        is_plan_mode: true,
      } as any,
    });

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        (input) => {
          expect(input.messages[0].role).toBe("system");
          expect(input.messages[0].content).toContain("todo.create");
          return [{ type: "text_delta", delta: "planned" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute({ ...run, harness_options: { mode: "pro", is_plan_mode: true } as any });
  });

  it("pauses for model clarification requests", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_clarify", thread_id: "thread_clarify" };
    store.createThread({
      id: "thread_clarify",
      org_id: "org_1",
      owner_user_id: "user_1",
      title: "Clarify",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    store.createRun(run);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          {
            type: "tool_call",
            id: "clarify_tc",
            name: "ask_clarification",
            input: {
              question: "Which file should I inspect?",
              clarification_type: "missing_info",
              options: ["/a.md", "/b.md"],
            },
          },
          { type: "completed" },
        ],
      ]),
    });

    const paused = await loop.execute(run);
    const eventTypes = store.listEvents(run.id).map((event) => event.type);

    expect(paused.status).toBe("waiting_input");
    expect(eventTypes).toContain("input.requested");
    expect(eventTypes).toContain("run.paused");
    expect(eventTypes).not.toContain("run.completed");
    expect(store.listEvents(run.id).find((event) => event.type === "input.requested")?.payload).toMatchObject({
      input_request_id: "clarify_run_clarify_clarify_tc",
      tool_call_id: "clarify_tc",
      prompt: "Which file should I inspect?",
      clarification_type: "missing_info",
      options: ["/a.md", "/b.md"],
    });
  });

  it("does not add todo planning guidance outside plan mode", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    store.createRun({ ...run, harness_options: { mode: "thinking" } as any });

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        (input) => {
          expect(input.messages.some((message) => message.content.includes("todo.create"))).toBe(false);
          return [{ type: "text_delta", delta: "ok" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute({ ...run, harness_options: { mode: "thinking" } as any });
  });

  it("injects recent tool results as model-only context", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = createRun();
    const threadId = "thread_tool_context";
    store.createThread({
      id: threadId,
      org_id: "org_1",
      owner_user_id: "user_1",
      title: "Tool context",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    store.createRun({ ...run, thread_id: threadId });
    eventWriter.write(run.id, threadId, "tool.completed", {
      tool_call_id: "tc_1",
      name: "todo.create",
      output: { id: "todo_1", title: "Ship it", status: "pending" },
    });

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      modelAdapter: new TestModelAdapter([
        (input) => {
          expect(input.messages[0].role).toBe("system");
          expect(input.messages[0].content).toContain("Recent tool results");
          expect(input.messages[0].content).toContain("todo.create");
          return [{ type: "text_delta", delta: "ok" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute({ ...run, thread_id: threadId });

    expect(store.listMessages(threadId).some((message) => message.role === "system")).toBe(false);
  });

  it("creates a context summary after long completed threaded runs", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const run = createRun();
    const threadId = "thread_summary";
    store.createThread({
      id: threadId,
      org_id: "org_1",
      owner_user_id: "user_1",
      title: "Summary thread",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    const storedRun = store.createRun({ ...run, thread_id: threadId, status: "completed" });
    for (let i = 0; i < 13; i += 1) {
      store.createMessage({
        id: `msg_summary_${i}`,
        thread_id: threadId,
        role: i % 2 === 0 ? "user" : "assistant",
        content: `Message ${i}`,
        run_id: run.id,
        workspace_paths: [],
        created_at: `2026-01-01T00:00:${String(i).padStart(2, "0")}Z`,
      });
    }

    await runTerminalProcessors({ store, eventWriter, run: storedRun });

    expect(store.getLatestContextSummary(threadId)?.summary).toContain("Message 0");
  });

  it("completes 20-tool-turn runs with pro mode beyond old fixed ceiling", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), harness_options: { mode: "pro" } as unknown as Record<string, unknown> };
    store.createRun(run);

    const toolTurns = Array.from({ length: 20 }, (_, index) => [
      { type: "tool_call" as const, id: `model_tc_${index}`, name: "workspace.list_files", input: { path: `/file_${index}.txt` } },
      { type: "completed" as const },
    ]);
    const loop = new ModelTurnLoop({
      store, eventWriter, capabilityRouter,
      modelAdapter: new TestModelAdapter([
        ...toolTurns,
        [{ type: "text_delta", delta: "done" }, { type: "completed" }],
      ]),
    });

    const completed = await loop.execute(run);
    expect(completed.status).toBe("completed");
  });

  it("pauses at 50 model requests with approval, not run.failed", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_limits_pause_test", harness_options: { mode: "pro" } as unknown as Record<string, unknown> };
    store.createRun(run);

    for (let i = 0; i < 50; i += 1) {
      eventWriter.write(run.id, null, EVENT_TYPES.CONTEXT_PACKET_BUILT, { total_messages: i });
    }

    const loop = new ModelTurnLoop({
      store, eventWriter, capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [{ type: "text_delta", delta: "should not be reached" }, { type: "completed" }],
      ]),
    });

    const paused = await loop.execute(run);
    expect(paused.status).toBe("waiting_approval");
    expect(paused.current_approval_id).toBeTruthy();
    const events = store.listEvents(run.id);
    expect(events.some((e) => e.type === EVENT_TYPES.APPROVAL_REQUESTED)).toBe(true);
    expect(events.some((e) => e.type === EVENT_TYPES.RUN_PAUSED)).toBe(true);
    expect(events.some((e) => e.type === EVENT_TYPES.RUN_FAILED)).toBe(false);
  });

  it("includes Run warnings in model context when limit.warning events exist", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_warnings_test" };
    store.createRun(run);

    eventWriter.write(run.id, null, EVENT_TYPES.LIMIT_WARNING, {
      kind: "model_requests", current: 40, limit: 50,
      message: "Approaching model request limit (40/50)",
    });

    const loop = new ModelTurnLoop({
      store, eventWriter, capabilityRouter,
      modelAdapter: new TestModelAdapter([
        (input) => {
          expect(input.messages[0].content).toContain("Run warnings:");
          expect(input.messages[0].content).toContain("model_requests");
          return [{ type: "text_delta", delta: "ok" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute(run);
  });

  it("pauses on 5th identical tool call with repeat_tool_call warning and no tool execution", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_repeat_pause" };
    store.createRun(run);

    for (let i = 0; i < 4; i += 1) {
      eventWriter.write(run.id, null, EVENT_TYPES.TOOL_PROPOSED, {
        tool_call_id: `prior_tc_${i}`, name: "workspace.write_file", input: { path: "/f.txt" },
      });
    }

    const loop = new ModelTurnLoop({
      store, eventWriter, capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          { type: "tool_call", id: "repeat_tc", name: "workspace.write_file", input: { path: "/f.txt" } },
          { type: "completed" },
        ],
      ]),
    });

    const paused = await loop.execute(run);
    expect(paused.status).toBe("waiting_approval");
    const events = store.listEvents(run.id);
    const toolProposed = events.filter((e) => e.type === EVENT_TYPES.TOOL_PROPOSED);
    expect(toolProposed).toHaveLength(4);
    expect(events.filter((e) => e.type === EVENT_TYPES.TOOL_STARTED)).toHaveLength(0);
    expect(events.some((e) => e.type === EVENT_TYPES.LIMIT_WARNING
      && (e.payload as Record<string, unknown>).kind === "repeat_tool_call")).toBe(true);
  });

  it("pauses before tool execution when 100 prior tool.started events exist", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_tool_limit_pause" };
    store.createRun(run);

    for (let i = 0; i < 100; i += 1) {
      eventWriter.write(run.id, null, EVENT_TYPES.TOOL_STARTED, {
        tool_call_id: `prior_tc_${i}`, name: "workspace.read_file",
      });
    }

    const loop = new ModelTurnLoop({
      store, eventWriter, capabilityRouter,
      modelAdapter: new TestModelAdapter([
        [
          { type: "tool_call", id: "new_tc", name: "workspace.write_file", input: { path: "/new.txt" } },
          { type: "completed" },
        ],
      ]),
    });

    const paused = await loop.execute(run);
    expect(paused.status).toBe("waiting_approval");
    const events = store.listEvents(run.id);
    const newProposed = events.filter((e) => e.type === EVENT_TYPES.TOOL_PROPOSED && (e.payload as Record<string, unknown>).tool_call_id === "new_tc");
    expect(newProposed).toHaveLength(0);
    expect(events.some((e) => e.type === EVENT_TYPES.APPROVAL_REQUESTED)).toBe(true);
  });
});
