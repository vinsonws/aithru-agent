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
    toolInputDrafts: [],
    reasoningSegments: [],
    assistantOutputSegments: [],
    todos: [],
    inlineRequests: [],
    presentations: [],
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
      modelStartedAt: "2026-06-23T00:00:10.000Z",
      modelCompletedAt: "2026-06-23T00:01:00.000Z",
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
        {
          id: "think_1",
          content: "准备写文件。",
          sequence: 11,
          lastSequence: 12,
          createdAt: "2026-06-23T00:00:11.000Z",
          completedAt: "2026-06-23T00:00:12.000Z",
        },
        {
          id: "think_2",
          content: "工具完成。",
          sequence: 16,
          lastSequence: 16,
          createdAt: "2026-06-23T00:00:16.000Z",
          completedAt: "2026-06-23T00:00:17.000Z",
        },
      ],
      assistantOutputSegments: [
        { id: "msg_assistant:output:13", role: "assistant", content: "马上创建。", sequence: 13, lastSequence: 13 },
        { id: "msg_assistant:output:17", role: "assistant", content: "已创建。", sequence: 17, lastSequence: 18 },
      ],
      toolCalls: [
        {
          id: "tool_1",
          toolName: "workspace.write_file",
          status: "completed",
          sequence: 14,
          lastSequence: 15,
          createdAt: "2026-06-23T00:00:14.000Z",
          updatedAt: "2026-06-23T00:00:15.000Z",
        },
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

  assert.deepEqual(
    timeline
      .filter((item) => item.kind === "message")
      .map((item) => ({
        content: item.message.content,
        showFooter: item.showFooter ?? true,
        footerContent: item.footerMessage?.content,
      })),
    [
      {
        content: "创建文件",
        showFooter: true,
        footerContent: undefined,
      },
      {
        content: "马上创建。",
        showFooter: false,
        footerContent: "马上创建。已创建。",
      },
      {
        content: "已创建。",
        showFooter: true,
        footerContent: "马上创建。已创建。",
      },
    ],
  );

  const processItems = timeline.filter((item) => item.kind === "assistantProcess");
  assert.deepEqual(
    processItems.map((item) => ({
      phase: item.phase,
      startedAt: item.startedAt,
      completedAt: item.completedAt,
      endedAt: item.endedAt,
    })),
    [
      {
        phase: "completed",
        startedAt: "2026-06-23T00:00:11.000Z",
        completedAt: "2026-06-23T00:00:12.000Z",
        endedAt: "2026-06-23T00:00:12.000Z",
      },
      {
        phase: "completed",
        startedAt: "2026-06-23T00:00:14.000Z",
        completedAt: "2026-06-23T00:00:17.000Z",
        endedAt: "2026-06-23T00:00:17.000Z",
      },
    ],
  );
});

test("buildChatTimeline leaves active mixed process timing incomplete", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      status: "running",
      toolCalls: [
        {
          id: "tool_1",
          toolName: "workspace.read_file",
          status: "completed",
          sequence: 10,
          lastSequence: 11,
          createdAt: "2026-06-23T00:00:10.000Z",
          updatedAt: "2026-06-23T00:00:11.000Z",
        },
      ],
      reasoningSegments: [
        {
          id: "think_1",
          content: "继续分析。",
          streaming: true,
          sequence: 12,
          lastSequence: 13,
          createdAt: "2026-06-23T00:00:12.000Z",
          updatedAt: "2026-06-23T00:00:13.000Z",
        },
      ],
    }),
  );

  const process = timeline.find((item) => item.kind === "assistantProcess");
  assert.equal(process?.kind, "assistantProcess");
  assert.equal(process.phase, "running");
  assert.equal(process.completedAt, undefined);
  assert.equal(process.endedAt, undefined);
});

test("buildChatTimeline gives terminal incomplete process a stable endedAt", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      status: "completed",
      modelCompletedAt: "2026-06-23T00:00:20.000Z",
      reasoningSegments: [
        {
          id: "think_1",
          content: "最后整理。",
          streaming: true,
          sequence: 12,
          lastSequence: 13,
          createdAt: "2026-06-23T00:00:12.000Z",
          updatedAt: "2026-06-23T00:00:13.000Z",
        },
      ],
    }),
  );

  const process = timeline.find((item) => item.kind === "assistantProcess");
  assert.equal(process?.kind, "assistantProcess");
  assert.equal(process.phase, "completed");
  assert.equal(process.completedAt, undefined);
  assert.equal(process.endedAt, "2026-06-23T00:00:20.000Z");
});

test("buildChatTimeline places workspace draft cards after reasoning before tool proposal", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      status: "running",
      modelStartedSequence: 10,
      messages: [{ id: "msg_user", role: "user", content: "创建文件", sequence: 2 }],
      reasoningSegments: [
        {
          id: "think_1",
          content: "准备写草稿。",
          streaming: true,
          sequence: 11,
          lastSequence: 12,
          createdAt: "2026-06-23T00:00:11.000Z",
          updatedAt: "2026-06-23T00:00:12.000Z",
        },
      ],
      toolInputDrafts: [
        {
          inputStreamId: "chat:0",
          toolCallId: "call_1",
          toolName: "workspace.write_file",
          inputText: '{"path":"/outputs/live.md","content":"# He',
          status: "streaming",
          sequence: 13,
          lastSequence: 14,
        },
      ],
      toolCalls: [
        {
          id: "call_1",
          toolName: "workspace.write_file",
          status: "proposed",
          sequence: 20,
          lastSequence: 20,
        },
      ],
    }),
  );

  const firstProcess = timeline.find((item) => item.kind === "assistantProcess");
  assert.equal(firstProcess?.kind, "assistantProcess");
  assert.equal(firstProcess.phase, "completed");
  assert.equal(firstProcess.endedAt, "2026-06-23T00:00:12.000Z");

  assert.deepEqual(
    timeline.map((item) => {
      if (item.kind === "message") return `message:${item.message.content}`;
      if (item.kind === "assistantProcess") {
        return `process:${item.steps.map((step) => step.kind === "tool" ? step.tool.toolName : step.content).join("|")}`;
      }
      if (item.kind === "draftGeneration") {
        return `draft:${item.draft.path}:${item.draft.content}`;
      }
      return item.kind;
    }),
    [
      "message:创建文件",
      "process:准备写草稿。",
      "draft:/outputs/live.md:# He",
      "process:workspace.write_file",
    ],
  );
});

test("buildChatTimeline keeps completed workspace draft cards before the real file card", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      status: "running",
      modelStartedSequence: 10,
      messages: [{ id: "msg_user", role: "user", content: "创建文件", sequence: 2 }],
      toolInputDrafts: [
        {
          inputStreamId: "chat:0",
          toolCallId: "call_1",
          toolName: "workspace.write_file",
          inputText: '{"path":"/outputs/live.md","content":"# Hello"}',
          status: "completed",
          sequence: 13,
          lastSequence: 14,
        },
      ],
      toolCalls: [
        {
          id: "call_1",
          toolName: "workspace.write_file",
          status: "completed",
          sequence: 20,
          lastSequence: 21,
        },
      ],
      presentations: [
        {
          id: "presentation_1",
          status: "ready",
          priority: "normal",
          title: "live.md",
          resource: { kind: "workspace_file", path: "/outputs/live.md" },
          surfaces: ["conversation"],
          preferredView: "markdown",
          availableViews: ["markdown", "source_text", "download"],
          sequence: 22,
          lastSequence: 22,
        },
      ],
    }),
  );

  assert.deepEqual(
    timeline.map((item) => item.kind),
    ["message", "draftGeneration", "assistantProcess", "presentation"],
  );
  const draft = timeline.find((item) => item.kind === "draftGeneration");
  assert.equal(draft?.draft.status, "completed");
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
      },
      {
        id: "msg_early",
        role: "user",
        content: "第一条",
        created_at: "2026-06-24T08:20:58.000Z",
        run_id: "run_early",
      },
      {
        id: "msg_mid",
        role: "assistant",
        content: "中间回复",
        created_at: "2026-06-24T08:44:56.000Z",
        run_id: "run_mid",
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
      },
      {
        id: "thread_assistant_1",
        role: "assistant",
        content: "记住了。",
        created_at: "2026-06-24T00:00:01.000Z",
        run_id: "run_old",
      },
      {
        id: "msg_current_user",
        role: "user",
        content: "继续",
        created_at: "2026-06-24T00:00:02.000Z",
        run_id: "run_new",
      },
    ],
    "run_new",
  );

  assert.deepEqual(
    timeline.map((item) => item.kind === "message" ? item.message.content : item.kind),
    ["先记住项目叫 Aithru。", "记住了。", "继续", "assistantProcess"],
  );
});

test("buildChatTimeline interleaves cards between tool completion and assistant output", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      modelStartedSequence: 10,
      runCompletedSequence: 30,
      messages: [{ id: "msg_user", role: "user", content: "创建文件", sequence: 2 }],
      reasoningSegments: [{ id: "think_1", content: "准备写文件。", sequence: 11, lastSequence: 12 }],
      toolCalls: [
        { id: "tool_1", toolName: "workspace.write_file", status: "completed", sequence: 14, lastSequence: 15 },
      ],
      presentations: [
        {
          id: "presentation_1",
          status: "ready",
          priority: "normal",
          title: "a.txt",
          resource: { kind: "workspace_file", path: "/a.txt" },
          surfaces: ["conversation"],
          preferredView: "source_text",
          availableViews: ["source_text", "download"],
          sequence: 16,
          lastSequence: 16,
        },
      ],
      assistantOutputSegments: [
        { id: "msg_assistant:output:17", role: "assistant", content: "已创建。", sequence: 17, lastSequence: 18 },
      ],
    }),
  );

  assert.deepEqual(
    timeline.map((item) => {
      if (item.kind === "message") return `message:${item.message.content}`;
      if (item.kind === "assistantProcess") return "process";
      if (item.kind === "presentation") return `presentation:${item.presentation.title}`;
      return item.kind;
    }),
    ["message:创建文件", "process", "presentation:a.txt", "message:已创建。", "completion"],
  );
});

test("buildChatTimeline shows presentations before assistant output starts", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      status: "running",
      modelStartedSequence: 10,
      messages: [{ id: "msg_user", role: "user", content: "创建文件", sequence: 2 }],
      reasoningSegments: [{ id: "think_1", content: "准备写文件。", sequence: 11, lastSequence: 12 }],
      toolCalls: [
        { id: "tool_1", toolName: "workspace.write_file", status: "completed", sequence: 14, lastSequence: 15 },
      ],
      presentations: [
        {
          id: "presentation_1",
          status: "ready",
          priority: "normal",
          title: "a.txt",
          resource: { kind: "workspace_file", path: "/a.txt" },
          surfaces: ["conversation"],
          preferredView: "source_text",
          availableViews: ["source_text", "download"],
          sequence: 16,
          lastSequence: 16,
        },
      ],
      assistantOutputSegments: [],
    }),
  );

  assert.deepEqual(
    timeline.map((item) => {
      if (item.kind === "message") return `message:${item.message.content}`;
      if (item.kind === "assistantProcess") return "process";
      if (item.kind === "presentation") return `presentation:${item.presentation.title}`;
      return item.kind;
    }),
    ["message:创建文件", "process", "presentation:a.txt"],
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
      },
      {
        id: "msg_old_assistant",
        role: "assistant",
        content: "文件检查完了。",
        created_at: "2026-06-24T00:00:01.000Z",
        run_id: "run_old",
      },
      {
        id: "msg_new_user",
        role: "user",
        content: "继续下一步",
        created_at: "2026-06-24T00:00:02.000Z",
        run_id: "run_new",
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
