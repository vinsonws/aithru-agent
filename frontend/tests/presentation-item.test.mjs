import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { build } from "esbuild";
import path from "node:path";
import { pathToFileURL } from "node:url";

async function loadPresentationItem() {
  const outfile = path.resolve(".tmp-tests/presentation-item.cjs");
  await build({
    entryPoints: ["src/features/chat/PresentationItem.tsx"],
    bundle: true,
    platform: "node",
    format: "cjs",
    jsx: "automatic",
    outfile,
    external: ["react", "react-dom/server"],
    alias: {
      "@/lib/utils": path.resolve("src/lib/utils.ts"),
    },
  });
  return import(pathToFileURL(outfile).href + `?t=${Date.now()}`);
}

test("PresentationItem renders only approved actions", async () => {
  const { PresentationItem } = await loadPresentationItem();
  const html = renderToStaticMarkup(
    React.createElement(PresentationItem, {
      presentation: {
        id: "presentation_1",
        title: "index.html",
        status: "ready",
        priority: "normal",
        resource: { kind: "artifact", id: "artifact_1" },
        surfaces: ["conversation", "side_panel"],
        preferredView: "html_preview",
        availableViews: ["html_preview", "source_text", "download"],
        actions: [
          { kind: "open_view", label: "Preview", view: "html_preview" },
          { kind: "download", label: "Download" },
        ],
      },
      onPreviewFile: () => {},
    }),
  );

  assert.match(html, /index\.html/);
  assert.match(html, /Preview/);
  assert.match(html, /Download/);
  assert.doesNotMatch(html, /DangerousComponent/);
});

test("PresentationItem hides preview when html_preview is not available", async () => {
  const { PresentationItem } = await loadPresentationItem();
  const html = renderToStaticMarkup(
    React.createElement(PresentationItem, {
      presentation: {
        id: "presentation_2",
        title: "notes.txt",
        status: "ready",
        priority: "normal",
        resource: { kind: "artifact", id: "artifact_2" },
        surfaces: ["conversation"],
        preferredView: "source_text",
        availableViews: ["source_text", "download"],
        actions: [{ kind: "download", label: "Download" }],
      },
      onPreviewFile: () => {},
    }),
  );

  assert.doesNotMatch(html, /Preview/);
  assert.match(html, /Download/);
});
