import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadPresentationEffects() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/presentationEffects.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("previewTargetForPresentationEffect resolves approved artifact preview effects", async () => {
  const { previewTargetForPresentationEffect } = await loadPresentationEffects();

  assert.equal(
    previewTargetForPresentationEffect({
      id: "presentation_1",
      status: "ready",
      priority: "normal",
      title: "index.html",
      resource: { kind: "artifact", id: "artifact_1" },
      surfaces: ["conversation", "side_panel"],
      preferredView: "html_preview",
      availableViews: ["html_preview", "source_text", "download"],
      effects: [{ kind: "open_panel", panel: "preview", mode: "soft" }],
      actions: [{ kind: "open_view", label: "Preview", view: "html_preview" }],
    }),
    "artifact-artifact_1",
  );
});

test("previewTargetForPresentationEffect ignores effects without a preview panel request", async () => {
  const { previewTargetForPresentationEffect } = await loadPresentationEffects();

  assert.equal(
    previewTargetForPresentationEffect({
      id: "presentation_2",
      status: "ready",
      priority: "normal",
      title: "index.html",
      resource: { kind: "artifact", id: "artifact_1" },
      surfaces: ["conversation"],
      preferredView: "html_preview",
      availableViews: ["html_preview", "source_text", "download"],
      effects: [{ kind: "open_panel", panel: "activity", mode: "soft" }],
      actions: [{ kind: "open_view", label: "Preview", view: "html_preview" }],
    }),
    null,
  );
});

test("presentationEffectKey includes the latest sequence to avoid duplicate effects", async () => {
  const { presentationEffectKey } = await loadPresentationEffects();

  assert.equal(
    presentationEffectKey({
      id: "presentation_1",
      status: "ready",
      priority: "normal",
      title: "index.html",
      resource: { kind: "artifact", id: "artifact_1" },
      surfaces: ["conversation"],
      preferredView: "html_preview",
      availableViews: ["html_preview", "source_text", "download"],
      sequence: 10,
      lastSequence: 12,
    }),
    "presentation_1:12",
  );
});
