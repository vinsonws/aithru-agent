import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadChatTimeline() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/chatTimeline.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

function baseState(patch = {}) {
  return {
    status: "completed",
    messages: [],
    toolCalls: [],
    reasoningSegments: [],
    assistantOutputSegments: [],
    todos: [],
    inlineRequests: [],
    ...patch,
  };
}

test("buildChatTimeline orders assistant process before final assistant reply", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      modelStartedSequence: 13,
      runCompletedSequence: 84,
      messages: [
        {
          id: "msg_user",
          role: "user",
          content: "你好",
          sequence: 2,
          completedSequence: 3,
        },
        {
          id: "msg_assistant",
          role: "assistant",
          content: "让我先看看工作区。",
          sequence: 15,
          completedSequence: 83,
        },
      ],
      toolCalls: [
        {
          id: "tool_1",
          toolName: "workspace.list_files",
          status: "completed",
          sequence: 36,
          lastSequence: 38,
        },
      ],
    }),
  );

  assert.deepEqual(
    timeline.map((item) => item.kind),
    ["message", "assistantProcess", "message", "completion"],
  );
  assert.equal(
    timeline[1].kind === "assistantProcess" && timeline[1].steps[0].kind === "tool" && timeline[1].steps[0].tool.toolName,
    "workspace.list_files",
  );
});

test("buildChatTimeline groups interleaved reasoning and tools into one assistant process", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      modelStartedSequence: 10,
      messages: [
        {
          id: "msg_user",
          role: "user",
          content: "分析一下",
          sequence: 2,
        },
        {
          id: "msg_assistant",
          role: "assistant",
          content: "可以，问题在消息流展示。",
          sequence: 40,
          completedSequence: 44,
        },
      ],
      reasoningSegments: [
        {
          id: "think_1",
          content: "先确认聊天组件结构。",
          sequence: 11,
          lastSequence: 11,
        },
        {
          id: "think_2",
          content: "工具结果回来后继续判断。",
          sequence: 21,
          lastSequence: 21,
        },
      ],
      toolCalls: [
        {
          id: "tool_1",
          toolName: "workspace.read_file",
          status: "completed",
          sequence: 15,
          lastSequence: 20,
        },
      ],
    }),
  );

  assert.deepEqual(
    timeline.map((item) => item.kind),
    ["message", "assistantProcess", "message"],
  );

  const process = timeline[1];
  assert.equal(process.kind, "assistantProcess");
  assert.deepEqual(
    process.steps.map((step) => step.kind === "tool" ? `tool:${step.tool.toolName}` : `reasoning:${step.content}`),
    [
      "reasoning:先确认聊天组件结构。",
      "tool:workspace.read_file",
      "reasoning:工具结果回来后继续判断。",
    ],
  );
});

test("buildChatTimeline interleaves assistant output segments with reasoning and tools", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      modelStartedSequence: 10,
      runCompletedSequence: 30,
      messages: [
        { id: "msg_user", role: "user", content: "创建文件", sequence: 2 },
        {
          id: "msg_assistant",
          role: "assistant",
          content: "马上创建。已创建。",
          sequence: 7,
          completedSequence: 29,
        },
      ],
      reasoningSegments: [
        { id: "think_1", content: "准备写文件。", sequence: 11, lastSequence: 12 },
        { id: "think_2", content: "工具完成。", sequence: 16, lastSequence: 16 },
      ],
      assistantOutputSegments: [
        { id: "msg_assistant:output:13", role: "assistant", content: "马上创建。", sequence: 13, lastSequence: 13 },
        { id: "msg_assistant:output:17", role: "assistant", content: "已创建。", sequence: 17, lastSequence: 18 },
      ],
      toolCalls: [
        { id: "tool_1", toolName: "workspace.write_file", status: "completed", sequence: 14, lastSequence: 15 },
      ],
    }),
  );

  assert.deepEqual(
    timeline.map((item) => {
      if (item.kind === "message") return `message:${item.message.content}`;
      if (item.kind === "assistantProcess") {
        return `process:${item.steps.map((step) => step.kind === "tool" ? step.tool.toolName : step.content).join("|")}`;
      }
      return item.kind;
    }),
    [
      "message:创建文件",
      "process:准备写文件。",
      "message:马上创建。",
      "process:workspace.write_file|工具完成。",
      "message:已创建。",
      "completion",
    ],
  );
});

test("buildChatTimeline keeps pending inline requests in event order", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      status: "waiting_input",
      messages: [{ id: "msg_user", role: "user", content: "Start", sequence: 2 }],
      inlineRequests: [{ kind: "input", id: "input_1", prompt: "More detail?", runId: "run_1", sequence: 5 }],
    }),
  );

  assert.deepEqual(
    timeline.map((item) => item.kind),
    ["message", "inlineRequest"],
  );
});

test("buildChatTimeline orders thread messages by created_at when API returns them out of order", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState(),
    [
      {
        id: "msg_late",
        role: "user",
        content: "最后一条",
        created_at: "2026-06-24T08:48:44.000Z",
        run_id: "run_late",
        artifact_ids: [],
      },
      {
        id: "msg_early",
        role: "user",
        content: "第一条",
        created_at: "2026-06-24T08:20:58.000Z",
        run_id: "run_early",
        artifact_ids: [],
      },
      {
        id: "msg_mid",
        role: "assistant",
        content: "中间回复",
        created_at: "2026-06-24T08:44:56.000Z",
        run_id: "run_mid",
        artifact_ids: [],
      },
    ],
    null,
  );

  assert.deepEqual(
    timeline.filter((item) => item.kind === "message").map((item) => item.message.content),
    ["第一条", "中间回复", "最后一条"],
  );
});

test("buildChatTimeline keeps previous thread messages around the active run", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      status: "running",
      modelStartedSequence: 10,
      messages: [{ id: "msg_current_user", role: "user", content: "继续", sequence: 2 }],
      reasoningSegments: [{ id: "think_1", content: "读取上下文。", sequence: 11, lastSequence: 11 }],
    }),
    [
      {
        id: "thread_user_1",
        role: "user",
        content: "先记住项目叫 Aithru。",
        created_at: "2026-06-24T00:00:00.000Z",
        run_id: "run_old",
        artifact_ids: [],
      },
      {
        id: "thread_assistant_1",
        role: "assistant",
        content: "记住了。",
        created_at: "2026-06-24T00:00:01.000Z",
        run_id: "run_old",
        artifact_ids: [],
      },
      {
        id: "msg_current_user",
        role: "user",
        content: "继续",
        created_at: "2026-06-24T00:00:02.000Z",
        run_id: "run_new",
        artifact_ids: [],
      },
    ],
    "run_new",
  );

  assert.deepEqual(
    timeline.map((item) => item.kind === "message" ? item.message.content : item.kind),
    ["先记住项目叫 Aithru。", "记住了。", "继续", "assistantProcess"],
  );
});

test("buildChatTimeline keeps completed run process when a later run is active", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      status: "running",
      messages: [{ id: "msg_new_user", role: "user", content: "继续下一步", sequence: 2 }],
      modelStartedSequence: 50,
    }),
    [
      {
        id: "msg_old_user",
        role: "user",
        content: "先检查文件",
        created_at: "2026-06-24T00:00:00.000Z",
        run_id: "run_old",
        artifact_ids: [],
      },
      {
        id: "msg_old_assistant",
        role: "assistant",
        content: "文件检查完了。",
        created_at: "2026-06-24T00:00:01.000Z",
        run_id: "run_old",
        artifact_ids: [],
      },
      {
        id: "msg_new_user",
        role: "user",
        content: "继续下一步",
        created_at: "2026-06-24T00:00:02.000Z",
        run_id: "run_new",
        artifact_ids: [],
      },
    ],
    "run_new",
    {
      run_old: baseState({
        modelStartedSequence: 10,
        reasoningSegments: [{ id: "think_old", content: "先看文件列表。", sequence: 11, lastSequence: 11 }],
        toolCalls: [{ id: "tool_old", toolName: "workspace.list_files", status: "completed", sequence: 12, lastSequence: 13 }],
      }),
    },
  );

  assert.deepEqual(
    timeline.map((item) => item.kind === "message" ? item.message.content : item.id),
    ["先检查文件", "assistant-process:run_old", "文件检查完了。", "继续下一步", "assistant-process"],
  );
  const oldProcess = timeline.find((item) => item.id === "assistant-process:run_old");
  assert.equal(oldProcess?.kind, "assistantProcess");
  assert.deepEqual(
    oldProcess.kind === "assistantProcess"
      ? oldProcess.steps.map((step) => step.kind === "tool" ? `tool:${step.tool.toolName}` : `reasoning:${step.content}`)
      : [],
    ["reasoning:先看文件列表。", "tool:workspace.list_files"],
  );
});
