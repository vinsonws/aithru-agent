import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunActivity() {
  const result = await esbuild.build({
    absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/runActivity.ts"],
    plugins: [
      {
        name: "run-activity-test-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/features\/chat\/useRunStream$/ }, () => ({
            path: "mock-use-run-stream",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-use-run-stream$/, namespace: "mock" }, () => ({
            contents: "export {};",
            loader: "js",
          }));
        },
      },
    ],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

function baseState(patch = {}) {
  return {
    status: "running",
    messages: [],
    toolCalls: [],
    todos: [],
    inlineRequests: [],
    ...patch,
  };
}

test("buildRunActivity summarizes todos, current step, and token usage", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const activity = buildRunActivity(
    baseState({
      todos: [
        { id: "todo_1", title: "Inspect frontend", status: "done" },
        { id: "todo_2", title: "Design command center", status: "in_progress" },
        { id: "todo_3", title: "Write implementation plan", status: "pending" },
      ],
      tokenUsage: { input: 100, output: 25, total: 125 },
    }),
  );

  assert.equal(activity.status, "running");
  assert.equal(activity.progress.done, 1);
  assert.equal(activity.progress.total, 3);
  assert.equal(activity.current?.title, "Design command center");
  assert.equal(activity.usageLabel, "125 tokens");
  assert.deepEqual(
    activity.items.map((item) => [item.id, item.status, item.title]),
    [
      ["todo_1", "completed", "Inspect frontend"],
      ["todo_2", "current", "Design command center"],
      ["todo_3", "next", "Write implementation plan"],
    ],
  );
});

test("buildRunActivity promotes waiting input and failed run states", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const waiting = buildRunActivity(
    baseState({
      status: "waiting_input",
      inlineRequests: [
        {
          kind: "input",
          id: "input_1",
          prompt: "What should the agent focus on?",
          runId: "run_1",
        },
      ],
    }),
  );

  assert.equal(waiting.current?.status, "waiting");
  assert.equal(waiting.current?.title, "What should the agent focus on?");

  const failed = buildRunActivity(
    baseState({
      status: "failed",
      error: "model profile metadata cannot include secret values",
    }),
  );

  assert.equal(failed.current?.status, "failed");
  assert.equal(failed.current?.title, "Run failed");
  assert.match(failed.current?.detail ?? "", /metadata cannot include secret values/);
});

test("buildRunCompanionBadges marks approvals, files, and trace attention", async () => {
  const { buildRunCompanionBadges } = await loadRunActivity();
  const badges = buildRunCompanionBadges(
    baseState({
      status: "waiting_approval",
      inlineRequests: [
        {
          kind: "approval",
          id: "approval_1",
          prompt: "Allow filesystem write?",
          approvalId: "approval_1",
          runId: "run_1",
        },
      ],
      toolCalls: [
        {
          id: "tool_1",
          toolName: "workspace.write",
          status: "completed",
          outputSummary: "Updated frontend/src/AppShell.tsx",
        },
        {
          id: "tool_2",
          toolName: "model",
          status: "failed",
          error: "Validation failed",
        },
      ],
    }),
  );

  assert.equal(badges.approvals, 1);
  assert.equal(badges.files, 1);
  assert.equal(badges.trace, 1);
});

test("running with no todos returns narrative 'Agent is working'", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const activity = buildRunActivity(baseState({ status: "running" }));
  assert.equal(activity.narrative.title, "Agent is working");
  assert.equal(activity.narrative.nextAction, "none");
});

test("waiting input returns next action Reply to continue", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const activity = buildRunActivity(
    baseState({
      status: "waiting_input",
      inlineRequests: [{ kind: "input", id: "i1", prompt: "What next?", runId: "r1" }],
    }),
  );
  assert.equal(activity.narrative.nextAction, "reply");
  assert.equal(activity.narrative.title, "What next?");
});

test("waiting approval returns next action Review approval", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const activity = buildRunActivity(
    baseState({
      status: "waiting_approval",
      inlineRequests: [{ kind: "approval", id: "a1", prompt: "Allow?", approvalId: "a1", runId: "r1" }],
    }),
  );
  assert.equal(activity.narrative.nextAction, "reviewApproval");
});

test("completed with file tools increments file badge", async () => {
  const { buildRunActivity, buildRunCompanionBadges } = await loadRunActivity();
  const activity = buildRunActivity(
    baseState({
      status: "completed",
      toolCalls: [
        { id: "t1", toolName: "workspace.write", status: "completed", outputSummary: "wrote file.ts" },
        { id: "t2", toolName: "read", status: "completed", outputSummary: "read file.ts" },
      ],
    }),
  );
  assert.equal(activity.narrative.title, "Run completed");
  assert.match(activity.narrative.detail ?? "", /files/);
  const badges = buildRunCompanionBadges(
    baseState({
      status: "completed",
      toolCalls: [
        { id: "t1", toolName: "workspace.write", status: "completed", outputSummary: "wrote file.ts" },
      ],
    }),
  );
  assert.ok(badges.files > 0);
});

test("failed tool appears in activity items before passive completed tools", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const activity = buildRunActivity(
    baseState({
      status: "running",
      toolCalls: [
        { id: "t1", toolName: "read", status: "completed", outputSummary: "ok" },
        { id: "t2", toolName: "write", status: "failed", error: "error" },
      ],
    }),
  );
  const failedItem = activity.items.find((i) => i.status === "failed");
  assert.ok(failedItem);
  assert.equal(failedItem?.title, "write");
});

test("token usage label still formats as 125 tokens", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const activity = buildRunActivity(baseState({ status: "completed", tokenUsage: { total: 125 } }));
  assert.equal(activity.usageLabel, "125 tokens");
});

test("toolCounts are populated correctly", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const activity = buildRunActivity(
    baseState({
      toolCalls: [
        { id: "t1", toolName: "read", status: "completed" },
        { id: "t2", toolName: "write", status: "failed", error: "err" },
        { id: "t3", toolName: "search", status: "started" },
      ],
    }),
  );
  assert.equal(activity.toolCounts.completed, 1);
  assert.equal(activity.toolCounts.failed, 1);
  assert.equal(activity.toolCounts.running, 1);
});
