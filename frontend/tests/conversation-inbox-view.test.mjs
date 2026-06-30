import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadInboxView() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/sidebar/conversationInboxView.ts"],
    plugins: [
      {
        name: "inbox-view-mocks",
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
          build.onResolve({ filter: /^@\/features\/chat\/runStatusCopy$/ }, () => ({
            path: "mock-run-status-copy",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-run-status-copy$/, namespace: "mock" }, () => ({
            contents: `
              export function humanizeRunStatus(status, options) {
                const fallbacks = {
                  idle: "Not started",
                  running: "Running",
                  queued: "Queued",
                  waiting_input: "Awaiting reply",
                  waiting_approval: "Approval needed",
                  completed: "Completed",
                  failed: "Failed",
                  cancelled: "Cancelled",
                };
                const tones = {
                  idle: "muted",
                  running: "live",
                  queued: "queued",
                  waiting_input: "waiting",
                  waiting_approval: "waiting",
                  completed: "success",
                  failed: "danger",
                  cancelled: "cancelled",
                };
                return {
                  status: status || "idle",
                  labelKey: "chat:status." + (status || "idle"),
                  fallback: fallbacks[status || "idle"] || status,
                  tone: tones[status || "idle"] || "muted",
                  primaryAction: status === "failed" && options?.error ? "openModelSettings" : undefined,
                };
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

function makeDashboardItem(overrides = {}) {
  return {
    thread: { id: "thread_1", title: null },
    summary: {
      thread_id: "thread_1",
      message_count: 0,
      run_count: 0,
      active_run_count: 0,
      waiting_input_run_count: 0,
      latest_message: null,
      latest_run: null,
      last_activity_at: null,
    },
    latest_run: null,
    needs_attention: false,
    attention_reasons: [],
    research_status: "none",
    research_degraded: false,
    last_activity_at: null,
    action_hints: [],
    action_count: 0,
    high_priority_action_count: 0,
    ...overrides,
  };
}

test("explicit thread title wins over generated fallbacks", async () => {
  const { getReadableThreadTitle } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_1", title: "Chat redesign" },
    summary: {
      thread_id: "thread_1",
      message_count: 1,
      run_count: 1,
      active_run_count: 0,
      waiting_input_run_count: 0,
      latest_message: { message_id: "m1", role: "user", content_preview: "do the thing", truncated: false, created_at: "2026-06-23T00:00:00Z" },
      latest_run: null,
      last_activity_at: "2026-06-23T00:00:00Z",
    },
  });
  assert.equal(getReadableThreadTitle(item), "Chat redesign");
});

test("missing title falls back to latest message content preview", async () => {
  const { getReadableThreadTitle } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_1", title: null },
    summary: {
      thread_id: "thread_1",
      message_count: 1,
      run_count: 1,
      active_run_count: 0,
      waiting_input_run_count: 0,
      latest_message: { message_id: "m1", role: "user", content_preview: "Fix the login bug", truncated: false, created_at: "2026-06-23T00:00:00Z" },
      latest_run: { run_id: "run_1", status: "completed", task_msg: "Fix bug", started_at: "2026-06-23T00:00:00Z" },
      last_activity_at: "2026-06-23T00:00:00Z",
    },
  });
  assert.equal(getReadableThreadTitle(item), "Fix the login bug");
});

test("no message preview falls back to latest run goal", async () => {
  const { getReadableThreadTitle } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_1", title: null },
    summary: {
      thread_id: "thread_1",
      message_count: 0,
      run_count: 1,
      active_run_count: 0,
      waiting_input_run_count: 0,
      latest_message: null,
      latest_run: { run_id: "run_1", status: "completed", task_msg: "Design the command center", started_at: "2026-06-23T00:00:00Z" },
      last_activity_at: "2026-06-23T00:00:00Z",
    },
  });
  assert.equal(getReadableThreadTitle(item), "Design the command center");
});

test("no readable source returns Untitled conversation", async () => {
  const { getReadableThreadTitle } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_1", title: null },
    summary: {
      thread_id: "thread_1",
      message_count: 0,
      run_count: 0,
      active_run_count: 0,
      waiting_input_run_count: 0,
      latest_message: null,
      latest_run: null,
      last_activity_at: null,
    },
  });
  assert.equal(getReadableThreadTitle(item), "Untitled conversation");
});

test("needs_attention items are grouped into attention group", async () => {
  const { buildConversationInboxRow } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_1", title: "Urgent" },
    needs_attention: true,
    high_priority_action_count: 1,
    last_activity_at: "2026-06-23T00:00:00Z",
  });
  const row = buildConversationInboxRow(item, { activePath: "/", now: new Date("2026-06-23T12:00:00Z") });
  assert.equal(row.needsAttention, true);
});

test("current-day activity is grouped under today", async () => {
  const { buildConversationInboxGroups } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_1", title: "Today task" },
    last_activity_at: "2026-06-23T10:00:00Z",
  });
  const groups = buildConversationInboxGroups([item], { activePath: "/", now: new Date("2026-06-23T12:00:00Z") });
  const today = groups.find((g) => g.id === "today");
  assert.ok(today);
  assert.equal(today.rows.length, 1);
});

test("inbox rows are sorted newest first inside groups", async () => {
  const { buildConversationInboxGroups } = await loadInboxView();
  const oldItem = makeDashboardItem({
    thread: { id: "thread_old", title: "Old task" },
    last_activity_at: "2026-06-23T09:00:00Z",
  });
  const newItem = makeDashboardItem({
    thread: { id: "thread_new", title: "New task" },
    last_activity_at: "2026-06-23T11:00:00Z",
  });

  const groups = buildConversationInboxGroups([oldItem, newItem], {
    activePath: "/",
    now: new Date("2026-06-23T12:00:00Z"),
  });

  assert.deepEqual(groups.find((g) => g.id === "today").rows.map((row) => row.id), [
    "thread_new",
    "thread_old",
  ]);
});

test("older items are grouped under earlier", async () => {
  const { buildConversationInboxGroups } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_1", title: "Old task" },
    last_activity_at: "2026-06-20T10:00:00Z",
  });
  const groups = buildConversationInboxGroups([item], { activePath: "/", now: new Date("2026-06-23T12:00:00Z") });
  const earlier = groups.find((g) => g.id === "earlier");
  assert.ok(earlier);
  assert.equal(earlier.rows.length, 1);
});

test("search filters by title, status label, subtitle, and action hint label", async () => {
  const { buildConversationInboxRow, matchesConversationQuery } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_1", title: "Searchable title" },
    last_activity_at: "2026-06-23T10:00:00Z",
  });
  const row = buildConversationInboxRow(item, { activePath: "/", now: new Date("2026-06-23T12:00:00Z") });

  assert.equal(matchesConversationQuery(row, "searchable"), true);
  assert.equal(matchesConversationQuery(row, "title"), true);
  assert.equal(matchesConversationQuery(row, "nonexistent"), false);
});

test("raw thread IDs are not used as primary titles when any readable signal exists", async () => {
  const { getReadableThreadTitle } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_with_readable_data", title: null },
    summary: {
      thread_id: "thread_with_readable_data",
      message_count: 1,
      run_count: 1,
      active_run_count: 0,
      waiting_input_run_count: 0,
      latest_message: { message_id: "m1", role: "user", content_preview: "some content", truncated: false, created_at: "2026-06-23T00:00:00Z" },
      latest_run: null,
      last_activity_at: "2026-06-23T00:00:00Z",
    },
  });
  const title = getReadableThreadTitle(item);
  assert.equal(title, "some content");
  assert.notEqual(title, "thread_with_readable_data");
});

test("thread run subroutes are marked active for the parent conversation", async () => {
  const { buildConversationInboxRow } = await loadInboxView();
  const item = makeDashboardItem({
    thread: { id: "thread_17", title: "Active run page" },
  });

  const row = buildConversationInboxRow(item, {
    activePath: "/threads/thread_17/runs/run_22",
    now: new Date("2026-06-23T12:00:00Z"),
  });

  assert.equal(row.active, true);
});

test("compact inbox time uses single-letter unit abbreviations", async () => {
  const { compactConversationTime } = await loadInboxView();
  const now = new Date("2026-06-23T12:00:00Z");

  assert.equal(compactConversationTime("2026-06-23T11:59:45Z", now), "15s");
  assert.equal(compactConversationTime("2026-06-23T11:57:00Z", now), "3m");
  assert.equal(compactConversationTime("2026-06-23T10:00:00Z", now), "2h");
  assert.equal(compactConversationTime("2026-06-20T12:00:00Z", now), "3d");
  assert.equal(compactConversationTime("2026-06-09T12:00:00Z", now), "2w");
  assert.equal(compactConversationTime(null, now), "—");
});
