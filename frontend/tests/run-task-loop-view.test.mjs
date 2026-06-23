import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunTaskLoopView() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/conversation/runTaskLoopView.ts"],
    plugins: [
      {
        name: "run-task-loop-view-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/lib\/api$/ }, () => ({
            path: "mock-api",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/chat\/runActivity$/ }, () => ({
            path: "mock-run-activity",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/chat\/composerState$/ }, () => ({
            path: "mock-composer-state",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-api$/, namespace: "mock" }, () => ({
            contents: "export {};",
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-run-activity$/, namespace: "mock" }, () => ({
            contents: `
              export function buildRunActivity(state) {
                return state.activity;
              }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-composer-state$/, namespace: "mock" }, () => ({
            contents: `
              export function inferPermissionPolicyFromScopes(scopes) {
                if ((scopes || []).includes("*")) return "auto_safe";
                if ((scopes || []).some((scope) => scope.endsWith(".write"))) return "ask";
                return "read_only";
              }
              export function getPermissionPolicy(id) {
                const map = {
                  ask: { id: "ask", labelKey: "chat:permission.ask", fallback: "Ask" },
                  auto_safe: { id: "auto_safe", labelKey: "chat:permission.autoSafe", fallback: "Auto-safe" },
                  read_only: { id: "read_only", labelKey: "chat:permission.readOnly", fallback: "Read-only" },
                };
                return map[id] || map.ask;
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

function makeRun(overrides = {}) {
  return {
    id: "run_1234",
    goal: "Fix login",
    scopes: ["agent.workspace.read", "agent.workspace.write"],
    status: "running",
    harness_options: { model_profile_key: "MiniMax-M2.7" },
    ...overrides,
  };
}

test("returns null when there is no active run", async () => {
  const { buildRunTaskLoopView } = await loadRunTaskLoopView();
  const view = buildRunTaskLoopView({ activeRun: null, streamState: null, modeLabel: "Auto" });
  assert.equal(view, null);
});

test("projects goal, mode, permission, model, and current activity", async () => {
  const { buildRunTaskLoopView } = await loadRunTaskLoopView();
  const view = buildRunTaskLoopView({
    activeRun: makeRun(),
    modeLabel: "Auto",
    streamState: {
      activity: {
        narrative: { title: "Reading files", detail: "auth.ts" },
        progress: { done: 1, total: 3 },
      },
    },
  });

  assert.equal(view.goal, "Fix login");
  assert.equal(view.modeLabel, "Auto");
  assert.equal(view.permission.fallback, "Ask");
  assert.equal(view.modelLabel, "MiniMax-M2.7");
  assert.equal(view.currentTitle, "Reading files");
  assert.equal(view.currentDetail, "auth.ts");
  assert.deepEqual(view.progress, { done: 1, total: 3 });
});

test("uses read only permission label for read scopes", async () => {
  const { buildRunTaskLoopView } = await loadRunTaskLoopView();
  const view = buildRunTaskLoopView({
    activeRun: makeRun({ scopes: ["agent.workspace.read", "agent.memory.read"] }),
    modeLabel: "Plan",
    streamState: { activity: { narrative: { title: "Inspecting" }, progress: { done: 0, total: 0 } } },
  });

  assert.equal(view.permission.fallback, "Read-only");
});
