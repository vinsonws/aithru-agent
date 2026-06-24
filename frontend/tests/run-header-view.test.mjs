import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunHeaderView() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/conversation/runHeaderView.ts"],
    plugins: [
      {
        name: "run-header-view-test-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/lib\/api$/ }, () => ({
            path: "mock-api",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/chat\/runStatusCopy$/ }, () => ({
            path: "mock-run-status-copy",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/chat\/composerState$/ }, () => ({
            path: "mock-composer-state",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-api$/, namespace: "mock" }, () => ({
            contents: `
              export type AgentRunStatus = "queued" | "running" | "waiting_approval" | "waiting_subagent" | "waiting_input" | "waiting_external_run" | "completed" | "failed" | "cancelled";
              export type AgentRun = { id: string; status: AgentRunStatus; taskMsg: string; scopes: string[]; harness_options?: { model?: string | null; model_profile_key?: string | null } | null };
              export type AgentThread = { id: string; title?: string | null };
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-run-status-copy$/, namespace: "mock" }, () => ({
            contents: `
              export function humanizeRunStatus(status, options) {
                const map = {
                  idle: { fallback: "Not started", tone: "muted", labelKey: "", primaryAction: undefined, failureCategory: undefined },
                  running: { fallback: "Running", tone: "live", labelKey: "", primaryAction: "stop" },
                  waiting_input: { fallback: "Awaiting reply", tone: "waiting", labelKey: "", primaryAction: "reply" },
                  waiting_approval: { fallback: "Approval needed", tone: "waiting", labelKey: "", primaryAction: "reviewApproval" },
                  completed: { fallback: "Completed", tone: "success", labelKey: "", primaryAction: "newFollowUp" },
                  failed: { fallback: "Failed", tone: "danger", labelKey: "", primaryAction: "retry" },
                  cancelled: { fallback: "Cancelled", tone: "cancelled", labelKey: "", primaryAction: "retry" },
                };
                const result = { ...(map[status] || map.idle) };
                if (result.fallback === "Failed" && options?.error) {
                  const lower = options.error.toLowerCase();
                  if (lower.includes("model profile") || lower.includes("api key") || lower.includes("model configuration")) {
                    result.failureCategory = "modelConfiguration";
                    result.primaryAction = "openModelSettings";
                  }
                }
                return result;
              }
              export function formatShortRunId(id) { return id ? id.split("_")[0] + "_" + (id.split("_")[1] || "").slice(0, 4) : ""; }
              export function formatRunSubline(input) {
                const parts = [];
                if (input.runId) parts.push(input.runId.split("_")[0] + "_" + (input.runId.split("_")[1] || "").slice(0, 4));
                if (input.threadId) parts.push(input.threadId.split("_")[0] + "_" + (input.threadId.split("_")[1] || "").slice(0, 4));
                if (input.mode) parts.push(input.mode);
                return parts.join(" · ");
              }
              export function classifyRunFailure(error) {
                if (!error) return "unknown";
                const l = error.toLowerCase();
                if (l.includes("model profile") || l.includes("api key") || l.includes("model configuration")) return "modelConfiguration";
                if (l.includes("approval") || l.includes("denied") || l.includes("permission")) return "approval";
                if (l.includes("tool") || l.includes("capability") || l.includes("workspace") || l.includes("sandbox")) return "capability";
                return "unknown";
              }
              export function isTerminalRunStatus(status) { return ["completed", "failed", "cancelled"].includes(status); }
              export function isActiveRunStatus(status) { return ["running", "queued", "waiting_input", "waiting_approval", "waiting_subagent", "waiting_external_approval", "waiting_external_run", "paused"].includes(status); }
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
                  ask: { labelKey: "chat:permission.ask", fallback: "Ask" },
                  auto_safe: { labelKey: "chat:permission.autoSafe", fallback: "Auto-safe" },
                  read_only: { labelKey: "chat:permission.readOnly", fallback: "Read-only" },
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

function makeThread(overrides = {}) {
  return { id: "thread_abcdef", title: "Test thread", ...overrides };
}

function makeRun(overrides = {}) {
  return { id: "run_123456789", status: "running", goal: "Fix the bug", scopes: ["agent.workspace.read", "agent.workspace.write"], harness_options: { model_profile_key: "gpt-4", model: "gpt-4" }, ...overrides };
}

test("running run exposes stop action", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ status: "running" }), streamStatus: "running", threadId: "thread_abcdef", modeLabel: "Auto" });
  assert.ok(view.actions.find((a) => a.kind === "stop"));
  assert.equal(view.status.fallback, "Running");
});

test("waiting input run exposes reply action", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ status: "waiting_input" }), streamStatus: "waiting_input", threadId: "thread_abcdef", modeLabel: "Auto" });
  assert.ok(view.actions.find((a) => a.kind === "reply"));
  assert.equal(view.status.fallback, "Awaiting reply");
});

test("waiting approval run exposes reviewApproval action", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ status: "waiting_approval" }), streamStatus: "waiting_approval", threadId: "thread_abcdef", modeLabel: "Auto" });
  assert.ok(view.actions.find((a) => a.kind === "reviewApproval"));
  assert.equal(view.status.fallback, "Approval needed");
});

test("failed model-configuration run exposes openModelSettings and viewTrace", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ status: "failed", goal: "task" }), streamStatus: "failed", streamError: "model profile is missing", threadId: "thread_abcdef", modeLabel: "Auto" });
  assert.ok(view.actions.find((a) => a.kind === "openModelSettings"));
  assert.ok(view.actions.find((a) => a.kind === "viewTrace"));
  assert.equal(view.status.fallback, "Failed");
});

test("failed non-configuration run exposes retry and viewTrace", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ status: "failed", goal: "task" }), streamStatus: "failed", streamError: "something went wrong", threadId: "thread_abcdef", modeLabel: "Auto" });
  assert.ok(view.actions.find((a) => a.kind === "retry"));
  assert.ok(view.actions.find((a) => a.kind === "viewTrace"));
});

test("completed run does not expose header actions", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ status: "completed", goal: "task" }), streamStatus: "completed", threadId: "thread_abcdef", modeLabel: "Auto" });
  assert.deepEqual(view.actions, []);
});

test("subline includes short run id, short thread id, and mode label", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ status: "running" }), streamStatus: "running", threadId: "thread_abcdef", modeLabel: "Plan" });
  assert.match(view.subline, /run_1234/);
  assert.match(view.subline, /thread_abc/);
  assert.match(view.subline, /Plan/);
});

test("permission label is inferred from run scopes", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view = buildRunHeaderView({
    thread: makeThread(),
    activeRun: makeRun({ scopes: ["agent.workspace.read", "agent.memory.read"] }),
    streamStatus: "running",
    threadId: "thread_abcdef",
    modeLabel: "Auto",
  });

  assert.equal(view.permissionLabel, "Read-only");
  assert.equal(view.permissionLabelKey, "chat:permission.readOnly");
});

test("model label uses model_profile_key then model then empty string", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view1 = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ harness_options: { model_profile_key: "my-profile", model: "gpt-4" } }), streamStatus: "running", threadId: "t1", modeLabel: "A" });
  assert.equal(view1.modelLabel, "my-profile");
  const view2 = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ harness_options: { model_profile_key: null, model: "gpt-4-turbo" } }), streamStatus: "running", threadId: "t1", modeLabel: "A" });
  assert.equal(view2.modelLabel, "gpt-4-turbo");
  const view3 = buildRunHeaderView({ thread: makeThread(), activeRun: makeRun({ harness_options: { model_profile_key: null, model: null } }), streamStatus: "running", threadId: "t1", modeLabel: "A" });
  assert.equal(view3.modelLabel, "");
});
