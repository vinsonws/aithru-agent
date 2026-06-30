import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunStreamModule() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/useRunStream.ts"],
    plugins: [
      {
        name: "mock-runtime-imports",
        setup(build) {
          build.onResolve({ filter: /^@\/lib\/api$/ }, () => ({
            path: "mock-api",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-api$/, namespace: "mock" }, () => ({
            contents: `
              export const runsApi = {
                events: async () => [],
                stream: async () => {},
              };
            `,
            loader: "js",
          }));
        },
      },
    ],
  });

  const module = await import(
    `data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`
  );
  return module;
}

async function loadReduceEvent() {
  const module = await loadRunStreamModule();
  return module.reduceEvent;
}

function state() {
  return {
    status: "idle",
    messages: [],
    toolCalls: [],
    toolInputDrafts: [],
    reasoningSegments: [],
    assistantOutputSegments: [],
    todos: [],
    inlineRequests: [],
    presentations: [],
  };
}

function event(type, payload, sequence = 1) {
  return {
    id: `event_${type}`,
    run_id: "run_1",
    thread_id: "thread_1",
    sequence,
    timestamp: "2026-06-23T00:00:00.000Z",
    type,
    source: { kind: "harness" },
    visibility: "user",
    redaction: "none",
    summary: null,
    payload,
  };
}

test("reduceEvent deduplicates replayed input requests", async () => {
  const reduceEvent = await loadReduceEvent();
  const request = event("input.requested", {
    input_request_id: "input_1",
    prompt: "What should the agent focus on?",
  });

  const once = reduceEvent(state(), request);
  const twice = reduceEvent(once, request);

  assert.equal(twice.status, "waiting_input");
  assert.deepEqual(twice.inlineRequests, [
    {
      kind: "input",
      id: "input_1",
      prompt: "What should the agent focus on?",
      runId: "run_1",
      sequence: 1,
      createdAt: "2026-06-23T00:00:00.000Z",
    },
  ]);
});

test("reduceEvent keeps event sequence metadata for chat ordering", async () => {
  const reduceEvent = await loadReduceEvent();
  const events = [
    event("message.created", { message_id: "msg_user", role: "user" }, 2),
    event("message.completed", { message_id: "msg_user", content: "你好" }, 3),
    event("model.started", {}, 13),
    event("message.created", { message_id: "msg_assistant", role: "assistant" }, 15),
    event("tool.started", { tool_call_id: "tool_1", tool_name: "workspace.list_files" }, 36),
    event("tool.completed", { tool_call_id: "tool_1", tool_name: "workspace.list_files", output: { files: [] } }, 38),
    event("message.completed", { message_id: "msg_assistant", content: "工作区是空的。" }, 83),
    event("run.completed", { status: "completed" }, 84),
  ];

  const projected = events.reduce((current, nextEvent) => reduceEvent(current, nextEvent), state());

  assert.equal(projected.modelStartedSequence, 13);
  assert.equal(projected.messages[0].sequence, 2);
  assert.equal(projected.messages[1].completedSequence, 83);
  assert.equal(projected.toolCalls[0].sequence, 36);
  assert.equal(projected.toolCalls[0].lastSequence, 38);
  assert.equal(projected.runCompletedSequence, 84);
});

test("reduceEvent accumulates and binds streamed tool input drafts", async () => {
  const { buildRunStreamState } = await loadRunStreamModule();
  const projected = buildRunStreamState([
    event(
      "tool.input_delta",
      {
        input_stream_id: "chat:0",
        tool_call_id: "call_1",
        index: 0,
        name: "workspace.write_file",
        input_delta: '{"path":"/outputs/live.md"',
      },
      10,
    ),
    event(
      "tool.input_delta",
      {
        input_stream_id: "chat:0",
        tool_call_id: "call_1",
        index: 0,
        name: "workspace.write_file",
        input_delta: ',"content":"Hello',
      },
      11,
    ),
    event(
      "tool.proposed",
      {
        input_stream_id: "chat:0",
        tool_call_id: "call_1",
        name: "workspace.write_file",
        input: { path: "/outputs/live.md", content: "Hello" },
      },
      12,
    ),
    event(
      "tool.completed",
      {
        tool_call_id: "call_1",
        name: "workspace.write_file",
        output: { path: "/outputs/live.md", version: 1 },
      },
      13,
    ),
  ]);

  assert.deepEqual(projected.toolInputDrafts, [
    {
      inputStreamId: "chat:0",
      toolCallId: "call_1",
      toolName: "workspace.write_file",
      inputText: '{"path":"/outputs/live.md","content":"Hello',
      status: "completed",
      sequence: 10,
      lastSequence: 13,
      createdAt: "2026-06-23T00:00:00.000Z",
      updatedAt: "2026-06-23T00:00:00.000Z",
    },
  ]);
});

test("completed workspace.write_file drafts trigger file query invalidation before terminal run state", async () => {
  const { buildRunStreamState, collectRunFileInvalidationKeys } = await loadRunStreamModule();
  const projected = buildRunStreamState([
    event(
      "tool.completed",
      {
        tool_call_id: "call_1",
        tool_name: "workspace.write_file",
        output: { path: "/outputs/live.md", version: 1 },
      },
      13,
    ),
    event("run.paused", { status: "paused" }, 14),
  ]);

  assert.deepEqual(collectRunFileInvalidationKeys("run_1", projected), [
    ["runs", "run_1", "snapshot", "files"],
    ["workspaces"],
  ]);
});

test("buildRunStreamState records the latest replayed event sequence", async () => {
  const { buildRunStreamState } = await loadRunStreamModule();
  const projected = buildRunStreamState([
    event("run.created", {}, 1),
    event("message.created", { message_id: "msg_user", role: "user" }, 7),
    event("message.delta", { message_id: "msg_user", delta: "你好" }, 9),
  ]);

  assert.equal(projected.lastEventSequence, 9);
});

test("followRunStreamUntilTerminal reconnects after a non-terminal stream close", async () => {
  const { followRunStreamUntilTerminal } = await loadRunStreamModule();
  const states = [];
  const streamAfterSequences = [];
  let streamCalls = 0;
  const client = {
    async stream(_runId, onEvent, _signal, afterSequence) {
      streamCalls += 1;
      streamAfterSequences.push(afterSequence);
      if (streamCalls === 1) {
        onEvent(event("run.started", { status: "running" }, 1));
        return;
      }
      onEvent(
        event(
          "run.failed",
          { status: "failed", error: { message: "tool exploded" } },
          2,
        ),
      );
    },
  };

  await followRunStreamUntilTerminal("run_1", client, {
    initialState: state(),
    reconnectDelayMs: 0,
    onState(nextState) {
      states.push(nextState);
    },
  });

  assert.equal(streamCalls, 2);
  assert.deepEqual(streamAfterSequences, [0, 1]);
  assert.equal(states.at(-1).status, "failed");
  assert.equal(states.at(-1).error, "tool exploded");
});

test("reduceEvent accumulates real reasoning segments without inventing content", async () => {
  const reduceEvent = await loadReduceEvent();
  const events = [
    event("model.started", {}, 10),
    event("reasoning.delta", { reasoning_id: "think_1", delta: "先查看项目结构。" }, 11),
    event("tool.started", { tool_call_id: "tool_1", tool_name: "workspace.list_files" }, 12),
    event("tool.completed", { tool_call_id: "tool_1", tool_name: "workspace.list_files", output: { files: [] } }, 13),
    event("reasoning.delta", { reasoning_id: "think_2", delta: "工具返回后继续判断。" }, 14),
    event("reasoning.completed", { reasoning_id: "think_2" }, 15),
  ];

  const projected = events.reduce((current, nextEvent) => reduceEvent(current, nextEvent), state());

  assert.deepEqual(
    projected.reasoningSegments.map((segment) => ({
      id: segment.id,
      content: segment.content,
      sequence: segment.sequence,
      lastSequence: segment.lastSequence,
      streaming: segment.streaming,
    })),
    [
      {
        id: "think_1",
        content: "先查看项目结构。",
        sequence: 11,
        lastSequence: 11,
        streaming: true,
      },
      {
        id: "think_2",
        content: "工具返回后继续判断。",
        sequence: 14,
        lastSequence: 15,
        streaming: false,
      },
    ],
  );
});

test("reduceEvent handles backend model reasoning deltas", async () => {
  const reduceEvent = await loadReduceEvent();
  const projected = reduceEvent(
    state(),
    event("model.reasoning_delta", { delta: "正在比较小数。" }, 11),
  );

  assert.equal(projected.reasoningSegments.length, 1);
  assert.equal(projected.reasoningSegments[0].content, "正在比较小数。");
  assert.equal(projected.reasoningSegments[0].streaming, true);
});

test("reduceEvent groups backend model reasoning deltas into one segment", async () => {
  const { buildRunStreamState } = await loadRunStreamModule();
  const projected = buildRunStreamState([
    { ...event("model.reasoning_delta", { delta: "用户" }, 11), id: "evt_reasoning_1" },
    { ...event("model.reasoning_delta", { delta: "发来问候" }, 12), id: "evt_reasoning_2" },
  ]);

  assert.equal(projected.reasoningSegments.length, 1);
  assert.equal(projected.reasoningSegments[0].content, "用户发来问候");
});

test("reduceEvent splits repeated reasoning id when a tool call happens between deltas", async () => {
  const reduceEvent = await loadReduceEvent();
  const events = [
    event("model.started", {}, 10),
    event("reasoning.delta", { reasoning_id: "think_1", delta: "先查看工作区。" }, 11),
    event("tool.started", { tool_call_id: "tool_1", tool_name: "workspace.list_files" }, 12),
    event("tool.completed", { tool_call_id: "tool_1", tool_name: "workspace.list_files", output: { files: [] } }, 13),
    event("reasoning.delta", { reasoning_id: "think_1", delta: "工作区为空，再搜索记忆。" }, 14),
    event("reasoning.completed", { reasoning_id: "think_1" }, 15),
  ];

  const projected = events.reduce((current, nextEvent) => reduceEvent(current, nextEvent), state());

  assert.deepEqual(
    projected.reasoningSegments.map((segment) => ({
      content: segment.content,
      sequence: segment.sequence,
      lastSequence: segment.lastSequence,
      streaming: segment.streaming,
    })),
    [
      {
        content: "先查看工作区。",
        sequence: 11,
        lastSequence: 11,
        streaming: false,
      },
      {
        content: "工作区为空，再搜索记忆。",
        sequence: 14,
        lastSequence: 15,
        streaming: false,
      },
    ],
  );
  assert.equal(projected.reasoningSegments[0].id, "think_1");
  assert.match(projected.reasoningSegments[1].id, /^think_1:chunk:14$/);
});

test("reduceEvent splits repeated reasoning id when assistant output happens between deltas", async () => {
  const reduceEvent = await loadReduceEvent();
  const events = [
    event("message.created", { message_id: "msg_assistant", role: "assistant" }, 10),
    event("reasoning.delta", { message_id: "msg_assistant", reasoning_id: "think_1", delta: "先构思。" }, 11),
    event("reasoning.completed", { message_id: "msg_assistant", reasoning_id: "think_1" }, 12),
    event("message.delta", { message_id: "msg_assistant", delta: "普通回复。" }, 13),
    event("reasoning.delta", { message_id: "msg_assistant", reasoning_id: "think_1", delta: "继续思考。" }, 14),
    event("reasoning.completed", { message_id: "msg_assistant", reasoning_id: "think_1" }, 15),
  ];

  const projected = events.reduce((current, nextEvent) => reduceEvent(current, nextEvent), state());

  assert.deepEqual(
    projected.reasoningSegments.map((segment) => ({
      content: segment.content,
      sequence: segment.sequence,
      lastSequence: segment.lastSequence,
      streaming: segment.streaming,
    })),
    [
      {
        content: "先构思。",
        sequence: 11,
        lastSequence: 12,
        streaming: false,
      },
      {
        content: "继续思考。",
        sequence: 14,
        lastSequence: 15,
        streaming: false,
      },
    ],
  );
  assert.equal(projected.reasoningSegments[0].id, "think_1");
  assert.match(projected.reasoningSegments[1].id, /^think_1:chunk:14$/);
});

test("reduceEvent splits assistant output when process events happen between deltas", async () => {
  const reduceEvent = await loadReduceEvent();
  const events = [
    event("message.created", { message_id: "msg_assistant", role: "assistant" }, 10),
    event("reasoning.delta", { message_id: "msg_assistant", reasoning_id: "think_1", delta: "准备写文件。" }, 11),
    event("reasoning.completed", { message_id: "msg_assistant", reasoning_id: "think_1" }, 12),
    event("message.delta", { message_id: "msg_assistant", delta: "马上创建。" }, 13),
    event("tool.started", { tool_call_id: "tool_1", tool_name: "workspace.write_file" }, 14),
    event("tool.completed", { tool_call_id: "tool_1", tool_name: "workspace.write_file", output: { path: "/a.txt" } }, 15),
    event("reasoning.delta", { message_id: "msg_assistant", reasoning_id: "think_1", delta: "工具完成。" }, 16),
    event("message.delta", { message_id: "msg_assistant", delta: "已创建。" }, 17),
    event("message.completed", { message_id: "msg_assistant", content: "马上创建。已创建。" }, 18),
  ];

  const projected = events.reduce((current, nextEvent) => reduceEvent(current, nextEvent), state());

  assert.deepEqual(
    projected.assistantOutputSegments.map((segment) => ({
      content: segment.content,
      sequence: segment.sequence,
      lastSequence: segment.lastSequence,
      streaming: segment.streaming,
    })),
    [
      {
        content: "马上创建。",
        sequence: 13,
        lastSequence: 13,
        streaming: false,
      },
      {
        content: "已创建。",
        sequence: 17,
        lastSequence: 18,
        streaming: false,
      },
    ],
  );
});

test("reduceEvent repairs assistant output segments from completed content", async () => {
  const reduceEvent = await loadReduceEvent();
  const events = [
    event("message.created", { message_id: "msg_assistant", role: "assistant" }, 10),
    event("reasoning.delta", { message_id: "msg_assistant", reasoning_id: "think_1", delta: "用户想要惊喜。" }, 11),
    event("reasoning.completed", { message_id: "msg_assistant", reasoning_id: "think_1" }, 12),
    event("message.delta", { message_id: "msg_assistant", delta: "'s do this!" }, 13),
    event("tool.started", { tool_call_id: "tool_1", tool_name: "skill.load" }, 14),
    event("tool.completed", { tool_call_id: "tool_1", tool_name: "skill.load", output: { skill: "surprise-me" } }, 15),
    event("message.delta", { message_id: "msg_assistant", delta: "me see what creative tools I can combine." }, 16),
    event("message.completed", {
      message_id: "msg_assistant",
      content: "Let's do this! Let me see what creative tools I can combine.",
    }, 17),
  ];

  const projected = events.reduce((current, nextEvent) => reduceEvent(current, nextEvent), state());

  assert.deepEqual(
    projected.assistantOutputSegments.map((segment) => segment.content),
    [
      "Let's do this!",
      " Let me see what creative tools I can combine.",
    ],
  );
});

test("buildRunStreamState projects replayed events for historical run process", async () => {
  const { buildRunStreamState } = await loadRunStreamModule();
  const projected = buildRunStreamState([
    event("run.created", { status: "queued" }, 1),
    event("model.started", {}, 10),
    event("reasoning.delta", { reasoning_id: "think_1", delta: "先看文件。" }, 11),
    event("tool.started", { tool_call_id: "tool_1", tool_name: "workspace.list_files" }, 12),
    event("tool.completed", { tool_call_id: "tool_1", tool_name: "workspace.list_files", output: { files: [] } }, 13),
    event("run.completed", { status: "completed" }, 20),
  ]);

  assert.equal(projected.status, "completed");
  assert.equal(projected.modelStartedSequence, 10);
  assert.equal(projected.reasoningSegments[0].content, "先看文件。");
  assert.equal(projected.toolCalls[0].toolName, "workspace.list_files");
});

test("revealRunStreamState releases streaming message text in small chunks", async () => {
  const { revealRunStreamState } = await loadRunStreamModule();
  const current = {
    ...state(),
    status: "running",
    messages: [
      { id: "msg_1", role: "assistant", content: "你好", streaming: true },
    ],
  };
  const target = {
    ...state(),
    status: "running",
    messages: [
      { id: "msg_1", role: "assistant", content: "你好，这是一段更长的回复", streaming: true },
    ],
  };

  const revealed = revealRunStreamState(current, target, { maxCharsPerTick: 3 });

  assert.equal(revealed.messages[0].content, "你好，这是");
});

test("revealRunStreamState hides later steps until earlier reasoning text is revealed", async () => {
  const { revealRunStreamState } = await loadRunStreamModule();
  const current = {
    ...state(),
    status: "running",
    reasoningSegments: [
      { id: "think_1", content: "先检", streaming: true, sequence: 11, lastSequence: 12 },
    ],
  };
  const target = {
    ...state(),
    status: "running",
    reasoningSegments: [
      {
        id: "think_1",
        content: "先检查组件状态，然后再调用工具。",
        streaming: false,
        sequence: 11,
        lastSequence: 15,
      },
      {
        id: "think_2",
        content: "工具后继续判断。",
        streaming: true,
        sequence: 17,
        lastSequence: 17,
      },
    ],
    toolCalls: [
      { id: "tool_1", toolName: "workspace.read_file", status: "started", sequence: 16, lastSequence: 16 },
    ],
  };

  const revealed = revealRunStreamState(current, target, { maxCharsPerTick: 3 });

  assert.equal(revealed.reasoningSegments[0].content, "先检查组件");
  assert.equal(revealed.reasoningSegments[0].streaming, true);
  assert.deepEqual(revealed.reasoningSegments.map((segment) => segment.id), ["think_1"]);
  assert.deepEqual(revealed.toolCalls, []);

  const caughtUp = revealRunStreamState(
    { ...current, reasoningSegments: [target.reasoningSegments[0]] },
    target,
    { maxCharsPerTick: 100 },
  );

  assert.deepEqual(caughtUp.reasoningSegments.map((segment) => segment.id), ["think_1", "think_2"]);
  assert.deepEqual(caughtUp.toolCalls.map((tool) => tool.id), ["tool_1"]);
});

test("reduceEvent projects presentation events into stream state", async () => {
  const reduceEvent = await loadReduceEvent();
  const projected = reduceEvent(
    state(),
    event(
      "presentation.created",
      {
        presentation: {
          id: "presentation_1",
          run_id: "run_1",
          thread_id: "thread_1",
          status: "ready",
          priority: "normal",
          title: "a.txt",
          resource: { kind: "workspace_file", path: "/a.txt" },
          surfaces: ["conversation"],
          preferred_view: "source_text",
          available_views: ["source_text", "download"],
          actions: [{ kind: "download", label: "Download" }],
          source: { created_by: "harness", tool_call_id: "tool_1" },
        },
      },
      16,
    ),
  );

  assert.equal(projected.presentations.length, 1);
  const p = projected.presentations[0];
  assert.equal(p.id, "presentation_1");
  assert.equal(p.status, "ready");
  assert.equal(p.title, "a.txt");
  assert.equal(p.preferredView, "source_text");
  assert.deepEqual(p.resource, { kind: "workspace_file", path: "/a.txt" });
  assert.deepEqual(p.surfaces, ["conversation"]);
  assert.equal(p.sequence, 16);
});

test("revealRunStreamState flushes remaining text when a run is terminal", async () => {
  const { revealRunStreamState } = await loadRunStreamModule();
  const current = {
    ...state(),
    status: "running",
    messages: [
      { id: "msg_1", role: "assistant", content: "你好", streaming: true },
    ],
  };
  const target = {
    ...state(),
    status: "completed",
    messages: [
      { id: "msg_1", role: "assistant", content: "你好，完整回复", streaming: false },
    ],
  };

  const revealed = revealRunStreamState(current, target, { maxCharsPerTick: 1 });

  assert.equal(revealed.messages[0].content, "你好，完整回复");
  assert.equal(revealed.status, "completed");
});
