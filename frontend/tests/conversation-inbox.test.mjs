import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function renderInbox(items, overrides = {}) {
  const resolveDir = fileURLToPath(new URL("..", import.meta.url));
  const fixture = `
    import React from "react";
    import { renderToStaticMarkup } from "react-dom/server";
    import { ConversationInbox } from "./src/features/sidebar/ConversationInbox";
    const items = ${JSON.stringify(items)};
    export default renderToStaticMarkup(
      React.createElement(ConversationInbox, {
        items,
        activePath: ${JSON.stringify(overrides.activePath ?? "/threads/thread_1")},
        locale: "en-US",
        loading: false,
        emptyLabel: "No conversations",
        query: ${JSON.stringify(overrides.query ?? "")},
      }),
    );
  `;

  const result = await esbuild.build({
    absWorkingDir: resolveDir,
    bundle: true,
    format: "cjs",
    jsx: "automatic",
    platform: "node",
    write: false,
    stdin: {
      contents: fixture,
      resolveDir,
      sourcefile: "conversation-inbox-fixture.tsx",
      loader: "tsx",
    },
    plugins: [
      {
        name: "conversation-inbox-test-mocks",
        setup(build) {
          build.onResolve({ filter: /^react-router-dom$/ }, () => ({
            path: "mock-router",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/scroll-area$/ }, () => ({
            path: "mock-scroll-area",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/input$/ }, () => ({
            path: "mock-input",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/dropdown-menu$/ }, () => ({
            path: "mock-dropdown-menu",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/lib\/utils$/ }, () => ({
            path: "mock-utils",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/lib\/api$/ }, () => ({
            path: "mock-api",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/chat\/runStatusCopy$/ }, () => ({
            path: "mock-run-status",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^react-i18next$/ }, () => ({
            path: "mock-react-i18next",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^\.\/conversationInboxView$/ }, () => ({
            path: "mock-inbox-view",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\// }, (args) => ({
            path: fileURLToPath(new URL(`../src/${args.path.slice(2)}`, import.meta.url)),
          }));
          build.onLoad({ filter: /^mock-router$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Link(props) {
                const { to, children, ...rest } = props;
                return React.createElement("a", { ...rest, href: to }, children);
              }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-scroll-area$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function ScrollArea(props) {
                const { viewportClassName, children, ...rest } = props;
                return React.createElement("div", { ...rest, "data-viewport-class": viewportClassName || "" }, children);
              }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-input$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Input(props) { return React.createElement("input", props); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-dropdown-menu$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function DropdownMenu(props) { return React.createElement("div", { "data-menu-root": true }, props.children); }
              export function DropdownMenuTrigger(props) { return React.Children.only(props.children); }
              export function DropdownMenuContent(props) {
                const { children, align, sideOffset, ...rest } = props;
                return React.createElement("div", { ...rest, "data-menu-content": true }, children);
              }
              export function DropdownMenuItem(props) {
                const { children, disabled, onSelect, ...rest } = props;
                return React.createElement("button", { ...rest, disabled, type: "button" }, children);
              }
              export function DropdownMenuSeparator(props) { return React.createElement("div", props); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-utils$/, namespace: "mock" }, () => ({
            contents: `
              export function cn(...classes) { return classes.filter(Boolean).join(" "); }
              export function relativeTime() { return "now"; }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-api$/, namespace: "mock" }, () => ({
            contents: `export type AgentThreadDashboardItem = Record<string, unknown>;`,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-run-status$/, namespace: "mock" }, () => ({
            contents: `
              export function humanizeRunStatus(status) {
                const map = { idle: "Not started", running: "Running", waiting_input: "Awaiting reply", waiting_approval: "Approval needed", completed: "Completed", failed: "Failed" };
                return { fallback: map[status] || status, tone: "muted", labelKey: "", primaryAction: undefined };
              }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-inbox-view$/, namespace: "mock" }, () => ({
            contents: `
              function isSameLocalDate(dateStr, now) {
                if (!dateStr) return false;
                const d = new Date(dateStr);
                return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
              }
              export function compactConversationTime() {
                return "3m";
              }
              export function buildConversationInboxGroups(items, options) {
                const now = options.now || new Date();
                const groups = [];
                const attention = items.filter(i => i.needs_attention || i.high_priority_action_count > 0);
                if (attention.length > 0) groups.push({ id: "attention", fallback: "Attention", rows: attention.map(i => makeRow(i, options)) });
                const today = items.filter(i => !attention.includes(i) && isSameLocalDate(i.last_activity_at, now));
                if (today.length > 0) groups.push({ id: "today", fallback: "Today", rows: today.map(i => makeRow(i, options)) });
                const earlier = items.filter(i => !attention.includes(i) && !today.includes(i));
                if (earlier.length > 0) groups.push({ id: "earlier", fallback: "Earlier", rows: earlier.map(i => makeRow(i, options)) });
                return groups;
              }
              function makeRow(item, options) {
                const title = item.thread.title || item.thread.id;
                return {
                  id: item.thread.id,
                  href: "/threads/" + item.thread.id,
                  title,
                  subtitle: "",
                  status: { fallback: "Running", tone: "live", labelKey: "" },
                  timestamp: item.last_activity_at,
                  needsAttention: !!item.needs_attention,
                  highPriorityActionCount: item.high_priority_action_count || 0,
                  active: options.activePath === "/threads/" + item.thread.id,
                };
              }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-react-i18next$/, namespace: "mock" }, () => ({
            contents: `
              export function useTranslation() {
                return { t: (_key, fallback) => fallback };
              }
            `,
            loader: "js",
          }));
        },
      },
    ],
  });

  const tmp = await mkdtemp(join(tmpdir(), "aithru-conversation-inbox-"));
  const outFile = join(tmp, "conversation-inbox.cjs");
  await writeFile(outFile, result.outputFiles[0].text, "utf8");
  try {
    const require = createRequire(import.meta.url);
    return require(outFile).default;
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
}

test("conversation inbox renders search input", async () => {
  const html = await renderInbox([]);
  assert.match(html, /<input/);
});

test("inbox rows render scan-friendly metadata for sidebar styling", async () => {
  const html = await renderInbox([
    {
      thread: { id: "thread_1", title: "Sidebar polish" },
      latest_run: { status: "running", created_at: "2026-06-23T00:00:00.000Z" },
      needs_attention: true,
      high_priority_action_count: 1,
      last_activity_at: new Date().toISOString(),
    },
  ]);

  assert.match(html, /data-testid="conversation-row"/);
  assert.match(html, /data-testid="conversation-row-menu-trigger"/);
  assert.match(html, /data-testid="conversation-status-dot"/);
  assert.match(html, /data-active="true"/);
  assert.match(html, /data-attention="true"/);
  assert.match(html, /flex min-h-0 min-w-0 flex-1 flex-col/);
  assert.match(html, /min-h-0 min-w-0 flex-1/);
  assert.match(html, /data-viewport-class="[^"]*!block/);
  assert.match(html, /data-viewport-class="[^"]*!w-full/);
  assert.match(html, /pl-2 pr-4/);
  assert.match(html, /h-9/);
  assert.match(html, /w-full max-w-full/);
  assert.match(html, /overflow-hidden/);
  assert.match(html, /hover:bg-secondary\/70/);
  assert.match(html, /ring-primary\/25/);
  assert.match(html, /max-w-20/);
  assert.doesNotMatch(html, />Running</);
  assert.doesNotMatch(html, /border-l-warning/);
  assert.doesNotMatch(html, /min-h-\[58px\]/);
});

test("inbox renders attention group when one row needs attention", async () => {
  const items = [
    {
      thread: { id: "thread_1", title: "Urgent task" },
      latest_run: { status: "running", created_at: "2026-06-23T00:00:00.000Z" },
      needs_attention: true,
      high_priority_action_count: 1,
      last_activity_at: "2026-06-23T00:00:00.000Z",
    },
    {
      thread: { id: "thread_2", title: "Normal task" },
      latest_run: { status: "completed", created_at: "2026-06-22T00:00:00.000Z" },
      needs_attention: false,
      high_priority_action_count: 0,
      last_activity_at: "2026-06-22T00:00:00.000Z",
    },
  ];
  const html = await renderInbox(items);
  assert.match(html, /Attention/);
});

test("inbox renders today group for current-day rows", async () => {
  const todayStr = new Date().toISOString();
  const items = [
    {
      thread: { id: "thread_1", title: "Today task" },
      latest_run: { status: "running", created_at: todayStr },
      needs_attention: false,
      high_priority_action_count: 0,
      last_activity_at: todayStr,
    },
    {
      thread: { id: "thread_2", title: "Yesterday task" },
      latest_run: { status: "completed", created_at: "2026-06-20T00:00:00.000Z" },
      needs_attention: false,
      high_priority_action_count: 0,
      last_activity_at: "2026-06-20T00:00:00.000Z",
    },
  ];
  const html = await renderInbox(items);
  assert.match(html, /Today/);
  assert.match(html, /Earlier/);
});
