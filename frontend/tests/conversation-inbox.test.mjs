import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { test } from "node:test";
import esbuild from "esbuild";

async function renderInbox() {
  const resolveDir = new URL("..", import.meta.url).pathname;
  const fixture = `
    import React from "react";
    import { renderToStaticMarkup } from "react-dom/server";
    import { ConversationInbox } from "./src/features/sidebar/ConversationInbox";
    const items = [
      {
        thread: { id: "thread_1", title: "Chat app redesign" },
        latest_run: { status: "running", created_at: "2026-06-23T00:00:00.000Z" },
        needs_attention: false,
        last_activity_at: "2026-06-23T00:00:00.000Z",
      },
      {
        thread: { id: "thread_2", title: "Meeting reminder" },
        latest_run: { status: "waiting_input", created_at: "2026-06-23T00:00:00.000Z" },
        needs_attention: true,
        last_activity_at: "2026-06-23T00:00:00.000Z",
      },
    ];
    export default renderToStaticMarkup(
      React.createElement(ConversationInbox, {
        items,
        activePath: "/threads/thread_1",
        locale: "en-US",
        loading: false,
        emptyLabel: "No conversations",
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
          build.onResolve({ filter: /^@\/lib\/utils$/ }, () => ({
            path: "mock-utils",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\// }, (args) => ({
            path: new URL(`../src/${args.path.slice(2)}`, import.meta.url).pathname,
          }));
          build.onLoad({ filter: /^mock-router$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Link(props) { return React.createElement("a", { href: props.to, className: props.className }, props.children); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-scroll-area$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function ScrollArea(props) { return React.createElement("div", props); }
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

test("conversation inbox renders active conversation and attention state", async () => {
  const html = await renderInbox();

  assert.match(html, /Chat app redesign/);
  assert.match(html, /Meeting reminder/);
  assert.match(html, /running/);
  assert.match(html, /waiting_input/);
});
