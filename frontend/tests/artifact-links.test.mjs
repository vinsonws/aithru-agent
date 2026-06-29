import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadArtifactLinks() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/artifactLinks.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

function stateWithArtifactPresentation(id) {
  return {
    status: "completed",
    messages: [],
    toolCalls: [],
    reasoningSegments: [],
    assistantOutputSegments: [],
    todos: [],
    inlineRequests: [],
    presentations: [
      {
        id: `presentation_${id}`,
        status: "ready",
        priority: "normal",
        title: "Starlight Wishes",
        resource: { kind: "artifact", id },
        surfaces: ["conversation"],
        preferredView: "html_preview",
        availableViews: ["html_preview", "source_text", "download"],
        actions: [{ kind: "open_view", label: "Preview", view: "html_preview" }],
      },
    ],
  };
}

test("resolveKnownArtifactHref rewrites known Aithru artifact public links to local content routes", async () => {
  const { resolveKnownArtifactHref } = await loadArtifactLinks();
  const known = new Set(["artifact_1"]);

  assert.equal(
    resolveKnownArtifactHref("https://aithru.ai/artifact/org_1/artifact_1", known),
    "/api/artifacts/artifact_1/content",
  );
});

test("resolveKnownArtifactHref leaves unknown Aithru artifact links unchanged", async () => {
  const { resolveKnownArtifactHref } = await loadArtifactLinks();
  const known = new Set(["artifact_1"]);

  assert.equal(
    resolveKnownArtifactHref("https://aithru.ai/artifact/org_1/artifact_missing", known),
    "https://aithru.ai/artifact/org_1/artifact_missing",
  );
});

test("resolveKnownArtifactHref leaves unrelated external links unchanged", async () => {
  const { resolveKnownArtifactHref } = await loadArtifactLinks();

  assert.equal(
    resolveKnownArtifactHref("https://example.com/artifact/org_1/artifact_1", new Set(["artifact_1"])),
    "https://example.com/artifact/org_1/artifact_1",
  );
});

test("resolveKnownArtifactHref leaves malformed encoded artifact ids unchanged", async () => {
  const { resolveKnownArtifactHref } = await loadArtifactLinks();

  assert.equal(
    resolveKnownArtifactHref("https://aithru.ai/artifact/org_1/artifact_%ZZ", new Set(["artifact_1"])),
    "https://aithru.ai/artifact/org_1/artifact_%ZZ",
  );
});

test("buildArtifactLinkResolver collects artifact ids from active run presentations", async () => {
  const { buildArtifactLinkResolver } = await loadArtifactLinks();
  const resolveHref = buildArtifactLinkResolver([stateWithArtifactPresentation("artifact_1")]);

  assert.equal(
    resolveHref("https://aithru.ai/artifact/org_1/artifact_1"),
    "/api/artifacts/artifact_1/content",
  );
});

test("rewriteKnownArtifactMarkdownLinks only rewrites known Aithru artifact links", async () => {
  const { buildArtifactLinkResolver, rewriteKnownArtifactMarkdownLinks } = await loadArtifactLinks();
  const resolveHref = buildArtifactLinkResolver([stateWithArtifactPresentation("artifact_1")]);

  assert.equal(
    rewriteKnownArtifactMarkdownLinks(
      [
        "[Known](https://aithru.ai/artifact/org_1/artifact_1)",
        "[Unknown](https://aithru.ai/artifact/org_1/artifact_2)",
        "[External](https://example.com/a)",
      ].join(" "),
      resolveHref,
    ),
    [
      "[Known](/api/artifacts/artifact_1/content)",
      "[Unknown](https://aithru.ai/artifact/org_1/artifact_2)",
      "[External](https://example.com/a)",
    ].join(" "),
  );
});

test("copyMessageContentWithArtifactLinks rewrites assistant messages only", async () => {
  const { buildArtifactLinkResolver, copyMessageContentWithArtifactLinks } = await loadArtifactLinks();
  const resolveHref = buildArtifactLinkResolver([stateWithArtifactPresentation("artifact_1")]);
  const content = "[Known](https://aithru.ai/artifact/org_1/artifact_1)";

  assert.equal(
    copyMessageContentWithArtifactLinks({ role: "assistant", content }, resolveHref),
    "[Known](/api/artifacts/artifact_1/content)",
  );
  assert.equal(
    copyMessageContentWithArtifactLinks({ role: "user", content }, resolveHref),
    content,
  );
});

test("rewriteKnownArtifactMarkdownLinks rewrites copied Markdown destinations", async () => {
  const { buildArtifactLinkResolver, rewriteKnownArtifactMarkdownLinks } = await loadArtifactLinks();
  const resolveHref = buildArtifactLinkResolver([stateWithArtifactPresentation("artifact_1")]);

  assert.equal(
    rewriteKnownArtifactMarkdownLinks(
      "[Starlight Wishes](https://aithru.ai/artifact/org_1/artifact_1)",
      resolveHref,
    ),
    "[Starlight Wishes](/api/artifacts/artifact_1/content)",
  );
});
