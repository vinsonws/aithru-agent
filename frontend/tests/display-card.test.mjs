import assert from "node:assert/strict";
import path from "node:path";
import { test } from "node:test";
import esbuild from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

async function loadDisplayCard() {
  const root = new URL("..", import.meta.url).pathname;
  const result = await esbuild.build({
    absWorkingDir: root,
    bundle: true,
    format: "esm",
    jsx: "automatic",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/DisplayCard.tsx"],
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
          build.onResolve({ filter: /^react-i18next$/ }, () => ({
            path: "mock-react-i18next",
            namespace: "mock",
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

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("DisplayCard only renders actions allowed by the card payload", async () => {
  const { DisplayCard } = await loadDisplayCard();
  const html = renderToStaticMarkup(
    React.createElement(DisplayCard, {
      card: {
        id: "card_1",
        type: "artifact",
        status: "ready",
        title: "report.md",
        surface: "conversation",
        resource: { kind: "artifact", id: "artifact_1" },
        actions: [{ kind: "preview", label: "Open preview" }],
      },
      onPreviewFile: () => {},
    }),
  );

  assert.match(html, /Open preview/);
  assert.doesNotMatch(html, /Download/);
});

test("DisplayCard hides preview when card actions do not allow preview", async () => {
  const { DisplayCard } = await loadDisplayCard();
  const html = renderToStaticMarkup(
    React.createElement(DisplayCard, {
      card: {
        id: "card_2",
        type: "file",
        status: "ready",
        title: "a.txt",
        surface: "conversation",
        resource: { kind: "workspace_file", path: "/a.txt" },
        actions: [],
      },
      onPreviewFile: () => {},
    }),
  );

  assert.doesNotMatch(html, /Preview/);
});
