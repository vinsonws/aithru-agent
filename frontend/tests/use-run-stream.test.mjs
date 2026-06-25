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
    reasoningSegments: [],
    assistantOutputSegments: [],
    todos: [],
    inlineRequests: [],
    displayCards: [],
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

test("buildRunStreamState records the latest replayed event sequence", async () => {
  const { buildRunStreamState } = await loadRunStreamModule();
  const projected = buildRunStreamState([
    event("run.created", {}, 1),
    event("message.created", { message_id: "msg_user", role: "user" }, 7),
    event("message.delta", { message_id: "msg_user", delta: "你好" }, 9),
  ]);

  assert.equal(projected.lastEventSequence, 9);
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

test("reduceEvent projects display card events into stream state", async () => {
  const reduceEvent = await loadReduceEvent();
  const projected = reduceEvent(
    state(),
    event(
      "display.card.created",
      {
        card: {
          id: "card_1",
          run_id: "run_1",
          thread_id: "thread_1",
          surface: "conversation",
          type: "file",
          status: "ready",
          title: "a.txt",
          resource: { kind: "workspace_file", path: "/a.txt" },
          actions: [{ kind: "preview", label: "Preview" }],
          source: { created_by: "harness", tool_call_id: "tool_1" },
        },
      },
      16,
    ),
  );

  assert.deepEqual(projected.displayCards, [
    {
      id: "card_1",
      type: "file",
      status: "ready",
      title: "a.txt",
      surface: "conversation",
      resource: { kind: "workspace_file", path: "/a.txt" },
      actions: [{ kind: "preview", label: "Preview" }],
      sequence: 16,
      lastSequence: 16,
      createdAt: "2026-06-23T00:00:00.000Z",
      updatedAt: "2026-06-23T00:00:00.000Z",
    },
  ]);
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
