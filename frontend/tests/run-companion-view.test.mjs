import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunCompanionView() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/inspection/runCompanionView.ts"],
    plugins: [
      {
        name: "run-companion-view-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/features\/chat\/runActivity$/ }, () => ({
            path: "mock-run-activity",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-run-activity$/, namespace: "mock" }, () => ({
            contents: `
              export function buildRunCompanionBadges(state) {
                return state.badges || { activity: 0, files: 0, approvals: 0, trace: 0 };
              }
            `,
            loader: "js",
          }));
        },
      },
    ],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("collapsed rail shows progress and no attention when quiet", async () => {
  const { buildRunCompanionRailView } = await loadRunCompanionView();
  const view = buildRunCompanionRailView({
    runStatus: "running",
    todoProgress: { done: 2, total: 5 },
    streamState: { badges: { activity: 0, files: 0, approvals: 0, trace: 0 } },
  });

  assert.equal(view.status, "running");
  assert.equal(view.statusTone, "live");
  assert.equal(view.progressLabel, "2/5");
  assert.equal(view.attentionCount, 0);
  assert.equal(view.hasAttention, false);
});

test("collapsed rail counts action attention but ignores passive files while running", async () => {
  const { buildRunCompanionRailView } = await loadRunCompanionView();
  const view = buildRunCompanionRailView({
    runStatus: "running",
    todoProgress: null,
    streamState: { badges: { activity: 1, files: 3, approvals: 2, trace: 1 } },
  });

  assert.equal(view.progressLabel, null);
  assert.equal(view.attentionCount, 4);
  assert.equal(view.hasAttention, true);
});

test("completed outputs can contribute attention", async () => {
  const { buildRunCompanionRailView } = await loadRunCompanionView();
  const view = buildRunCompanionRailView({
    runStatus: "completed",
    todoProgress: { done: 3, total: 3 },
    streamState: { badges: { activity: 0, files: 2, approvals: 0, trace: 0 } },
  });

  assert.equal(view.statusTone, "success");
  assert.equal(view.attentionCount, 2);
  assert.equal(view.hasAttention, true);
});
