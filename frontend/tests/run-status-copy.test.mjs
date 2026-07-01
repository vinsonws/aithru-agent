import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunStatusCopy() {
  const result = await esbuild.build({
    absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/runStatusCopy.ts"],
    plugins: [
      {
        name: "run-status-copy-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/lib\/api$/ }, () => ({
            path: "mock-api",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-api$/, namespace: "mock" }, () => ({
            contents:
              'export type AgentRunStatus = "queued" | "running" | "waiting_approval" | "waiting_subagent" | "waiting_input" | "waiting_external_run" | "completed" | "failed" | "cancelled";',
            loader: "js",
          }));
        },
      },
    ],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("humanizeRunStatus('idle') returns Not started with muted tone", async () => {
  const { humanizeRunStatus } = await loadRunStatusCopy();
  const result = humanizeRunStatus("idle");
  assert.equal(result.fallback, "Not started");
  assert.equal(result.tone, "muted");
  assert.equal(result.labelKey, "chat:status.notStarted");
});

test("humanizeRunStatus('running') returns Running with live tone and stop action", async () => {
  const { humanizeRunStatus } = await loadRunStatusCopy();
  const result = humanizeRunStatus("running");
  assert.equal(result.fallback, "Running");
  assert.equal(result.tone, "live");
  assert.equal(result.primaryAction, "stop");
});

test("humanizeRunStatus('waiting_input') returns Awaiting reply and reply action", async () => {
  const { humanizeRunStatus } = await loadRunStatusCopy();
  const result = humanizeRunStatus("waiting_input");
  assert.equal(result.fallback, "Awaiting reply");
  assert.equal(result.primaryAction, "reply");
});

test("humanizeRunStatus('waiting_approval') returns Approval needed and reviewApproval action", async () => {
  const { humanizeRunStatus } = await loadRunStatusCopy();
  const result = humanizeRunStatus("waiting_approval");
  assert.equal(result.fallback, "Approval needed");
  assert.equal(result.primaryAction, "reviewApproval");
});

test("humanizeRunStatus('failed') with model error returns modelConfiguration failure and openModelSettings action", async () => {
  const { humanizeRunStatus } = await loadRunStatusCopy();
  const result = humanizeRunStatus("failed", {
    error: "model profile metadata cannot include secret values",
  });
  assert.equal(result.fallback, "Failed");
  assert.equal(result.tone, "danger");
  assert.equal(result.failureCategory, "modelConfiguration");
  assert.equal(result.primaryAction, "openModelSettings");
});

test("formatShortRunId shortens run ids", async () => {
  const { formatShortRunId } = await loadRunStatusCopy();
  assert.equal(formatShortRunId("run_123456789"), "run_1234");
});

test("formatShortRunId handles null/undefined", async () => {
  const { formatShortRunId } = await loadRunStatusCopy();
  assert.equal(formatShortRunId(null), "");
  assert.equal(formatShortRunId(undefined), "");
});

test("formatRunSubline includes short run id, short thread id, and mode", async () => {
  const { formatRunSubline } = await loadRunStatusCopy();
  const result = formatRunSubline({
    runId: "run_123456789",
    threadId: "thread_abcdef",
    mode: "Auto",
  });
  assert.match(result, /run_1234/);
  assert.match(result, /thread_abc/);
  assert.match(result, /Auto/);
});

test("isTerminalRunStatus returns true for completed, failed, cancelled", async () => {
  const { isTerminalRunStatus } = await loadRunStatusCopy();
  assert.equal(isTerminalRunStatus("completed"), true);
  assert.equal(isTerminalRunStatus("failed"), true);
  assert.equal(isTerminalRunStatus("cancelled"), true);
  assert.equal(isTerminalRunStatus("running"), false);
  assert.equal(isTerminalRunStatus("idle"), false);
});

test("isActiveRunStatus returns true for running and waiting states", async () => {
  const { isActiveRunStatus } = await loadRunStatusCopy();
  assert.equal(isActiveRunStatus("running"), true);
  assert.equal(isActiveRunStatus("waiting_input"), true);
  assert.equal(isActiveRunStatus("waiting_approval"), true);
  assert.equal(isActiveRunStatus("completed"), false);
  assert.equal(isActiveRunStatus("idle"), false);
});

test("classifyRunFailure categorizes by error message patterns", async () => {
  const { classifyRunFailure } = await loadRunStatusCopy();
  assert.equal(classifyRunFailure("model profile is missing"), "modelConfiguration");
  assert.equal(classifyRunFailure("invalid api key"), "modelConfiguration");
  assert.equal(classifyRunFailure("base_url not configured"), "modelConfiguration");
  assert.equal(classifyRunFailure("approval denied by user"), "approval");
  assert.equal(classifyRunFailure("permission not granted"), "approval");
  assert.equal(classifyRunFailure("tool capability not found"), "capability");
  assert.equal(classifyRunFailure("workspace is full"), "capability");
  assert.equal(classifyRunFailure("random unknown error"), "unknown");
  assert.equal(classifyRunFailure(null), "unknown");
  assert.equal(classifyRunFailure(undefined), "unknown");
});
