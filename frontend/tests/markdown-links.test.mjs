import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

async function loadMarkdown() {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const result = await esbuild.build({
    absWorkingDir: root,
    bundle: true,
    format: "esm",
    jsx: "automatic",
    platform: "node",
    write: false,
    entryPoints: ["src/components/Markdown.tsx"],
    plugins: [
      {
        name: "mock-runtime-imports",
        setup(build) {
          build.onResolve({ filter: /^@\/lib\/utils$/ }, () => ({
            path: "mock-utils",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\// }, (args) => ({
            path: path.join(root, "src", args.path.slice(2)),
          }));
          build.onLoad({ filter: /^mock-utils$/, namespace: "mock" }, () => ({
            contents: `
              export function cn(...values) {
                return values.filter(Boolean).join(" ");
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

test("Markdown applies resolveLinkHref to anchor hrefs", async () => {
  const { Markdown } = await loadMarkdown();
  const html = renderToStaticMarkup(
    React.createElement(
      Markdown,
      {
        resolveLinkHref: (href) =>
          href === "https://example.com/workspace/ws1/reports/report.md"
            ? "/api/workspaces/ws1/files/reports/report.md/content"
            : href,
      },
      "[Report](https://example.com/workspace/ws1/reports/report.md)",
    ),
  );

  assert.match(html, /href="\/api\/workspaces\/ws1\/files\/reports\/report\.md\/content"/);
  assert.doesNotMatch(html, /href="https:\/\/example\.com\/workspace\/ws1\/reports\/report\.md"/);
});

test("Markdown does not leak react-markdown node props onto anchors", async () => {
  const { Markdown } = await loadMarkdown();
  const html = renderToStaticMarkup(
    React.createElement(
      Markdown,
      { resolveLinkHref: (href) => href },
      "[Example](https://example.com)",
    ),
  );

  assert.doesNotMatch(html, /node="\[object Object\]"/);
});
