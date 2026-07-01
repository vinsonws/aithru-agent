import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadSelectionModule() {
  const result = await esbuild.build({
    absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/conversation/activeRunSelection.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("resolveActiveRunId ignores a selected run from another thread", async () => {
  const { resolveActiveRunId } = await loadSelectionModule();

  assert.equal(
    resolveActiveRunId({
      threadId: "thread_b",
      routeRunId: null,
      selectedRun: { threadId: "thread_a", runId: "run_from_a" },
      runs: [{ id: "run_from_b" }],
    }),
    "run_from_b",
  );
});

test("resolveActiveRunId ignores stale run query data from another thread", async () => {
  const { resolveActiveRunId } = await loadSelectionModule();

  assert.equal(
    resolveActiveRunId({
      threadId: "thread_b",
      routeRunId: null,
      selectedRun: null,
      runs: [{ id: "run_from_a", thread_id: "thread_a" }],
    }),
    null,
  );
});

test("resolveActiveRunId keeps the selected run when it belongs to the current thread", async () => {
  const { resolveActiveRunId } = await loadSelectionModule();

  assert.equal(
    resolveActiveRunId({
      threadId: "thread_a",
      routeRunId: null,
      selectedRun: { threadId: "thread_a", runId: "new_run" },
      runs: [{ id: "older_run" }],
    }),
    "new_run",
  );
});

test("resolveActiveRunId prefers explicit run routes", async () => {
  const { resolveActiveRunId } = await loadSelectionModule();

  assert.equal(
    resolveActiveRunId({
      threadId: "thread_a",
      routeRunId: "route_run",
      selectedRun: { threadId: "thread_a", runId: "selected_run" },
      runs: [{ id: "latest_run" }],
    }),
    "route_run",
  );
});
