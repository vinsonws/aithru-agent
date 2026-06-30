import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunFilesView() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/inspection/runFilesView.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("workspace output files expose workspace download and preview urls", async () => {
  const { buildRunFileViews } = await loadRunFilesView();
  const views = buildRunFileViews({
    workspaceId: "ws1",
    workspaceFiles: [{ path: "reports/report.md", size: 100, media_type: "text/markdown" }],
  });
  assert.equal(views.length, 1);
  assert.equal(views[0].kind, "output_file");
  assert.equal(views[0].href, "/api/workspaces/ws1/files/reports/report.md/download");
  assert.equal(views[0].previewHref, "/api/workspaces/ws1/files/reports/report.md/content");
  assert.equal(views[0].canDownload, true);
});

test("workspace output and modified files are classified from path", async () => {
  const { buildRunFileViews } = await loadRunFilesView();
  const views = buildRunFileViews({
    workspaceFiles: [
      { path: "reports/report.md", size: 100 },
      { path: "notes/raw.txt", size: 50 },
    ],
  });

  assert.deepEqual(
    views.map((view) => [view.kind, view.path]),
    [
      ["output_file", "reports/report.md"],
      ["modified_file", "notes/raw.txt"],
    ],
  );
});

test("file type labels are inferred from media type and extension", async () => {
  const { inferFileTypeLabel } = await loadRunFilesView();
  assert.equal(inferFileTypeLabel({ name: "image.png", mediaType: "image/png" }), "Image");
  assert.equal(inferFileTypeLabel({ name: "doc.md" }), "Markdown");
  assert.equal(inferFileTypeLabel({ name: "data.json" }), "JSON");
  assert.equal(inferFileTypeLabel({ name: "component.tsx" }), "TypeScript");
  assert.equal(inferFileTypeLabel({ name: "script.py" }), "Python");
  assert.equal(inferFileTypeLabel({ name: "readme.txt" }), "Text");
  assert.equal(inferFileTypeLabel({ name: "unknown.xyz" }), "File");
});

test("empty snapshot returns an empty-state view", async () => {
  const { buildRunFileViews } = await loadRunFilesView();
  const views = buildRunFileViews({});
  assert.equal(views.length, 0);
});

test("image files receive image type", async () => {
  const { inferFileTypeLabel } = await loadRunFilesView();
  assert.equal(inferFileTypeLabel({ name: "screenshot.png" }), "Image");
  assert.equal(inferFileTypeLabel({ name: "photo.jpg" }), "Image");
  assert.equal(inferFileTypeLabel({ name: "graph.svg", mediaType: "image/svg+xml" }), "Image");
});

test("markdown, JSON, TypeScript, Python, and plain text receive readable type labels", async () => {
  const { inferFileTypeLabel } = await loadRunFilesView();
  assert.equal(inferFileTypeLabel({ name: "readme.md" }), "Markdown");
  assert.equal(inferFileTypeLabel({ name: "config.json" }), "JSON");
  assert.equal(inferFileTypeLabel({ name: "app.ts" }), "TypeScript");
  assert.equal(inferFileTypeLabel({ name: "main.py" }), "Python");
  assert.equal(inferFileTypeLabel({ name: "notes.txt" }), "Text");
});

test("preview kinds are inferred for supported output types", async () => {
  const { previewKindForFile, languageForFile } = await loadRunFilesView();

  assert.equal(previewKindForFile({ name: "report.md" }), "markdown");
  assert.equal(previewKindForFile({ name: "data.json" }), "json");
  assert.equal(previewKindForFile({ name: "chart.png", mediaType: "image/png" }), "image");
  assert.equal(previewKindForFile({ name: "main.py" }), "code");
  assert.equal(previewKindForFile({ name: "notes.txt" }), "text");
  assert.equal(previewKindForFile({ name: "final.md" }), "markdown");
  assert.equal(previewKindForFile({ name: "archive.zip" }), "unsupported");
  assert.equal(languageForFile("main.py"), "python");
  assert.equal(languageForFile("component.tsx"), "typescript");
});

test("buildDraftWorkspaceFiles extracts workspace write_file partial content", async () => {
  const { buildDraftWorkspaceFiles } = await loadRunFilesView();
  const drafts = buildDraftWorkspaceFiles([
    {
      inputStreamId: "chat:0",
      toolCallId: "call_1",
      toolName: "workspace.write_file",
      inputText: '{"path":"/outputs/live.html","content":"<h1>Hello',
      status: "streaming",
      lastSequence: 11,
    },
  ]);

  assert.deepEqual(drafts, [
    {
      id: "ws-/outputs/live.html",
      path: "/outputs/live.html",
      name: "live.html",
      content: "<h1>Hello",
      sourceToolCallId: "call_1",
      sourceInputStreamId: "chat:0",
      status: "streaming",
      lastSequence: 11,
    },
  ]);
});

test("buildRunFileViews includes draft files until a real file exists", async () => {
  const { buildRunFileViews } = await loadRunFilesView();
  const draftWorkspaceFiles = [
    {
      id: "ws-/outputs/live.md",
      path: "/outputs/live.md",
      name: "live.md",
      content: "# Live",
      sourceInputStreamId: "chat:0",
      status: "streaming",
      lastSequence: 11,
    },
  ];

  const withDraft = buildRunFileViews({ draftWorkspaceFiles });
  assert.equal(withDraft.length, 1);
  assert.equal(withDraft[0].id, "ws-/outputs/live.md");
  assert.equal(withDraft[0].isDraft, true);
  assert.equal(withDraft[0].draftContent, "# Live");
  assert.equal(withDraft[0].canDownload, false);
  assert.equal(withDraft[0].previewKind, "markdown");

  const withRealFile = buildRunFileViews({
    workspaceId: "ws1",
    workspaceFiles: [{ path: "/outputs/live.md", size: 8, media_type: "text/markdown" }],
    draftWorkspaceFiles,
  });
  assert.equal(withRealFile.length, 1);
  assert.equal(withRealFile[0].isDraft, undefined);
  assert.equal(withRealFile[0].href, "/api/workspaces/ws1/files/outputs/live.md/download");
});

test("formatFileSize formats bytes correctly", async () => {
  const { formatFileSize } = await loadRunFilesView();
  assert.equal(formatFileSize(0), "0 B");
  assert.equal(formatFileSize(500), "500 B");
  assert.equal(formatFileSize(2048), "2 KB");
  assert.equal(formatFileSize(1048576), "1 MB");
  assert.equal(formatFileSize(null), undefined);
  assert.equal(formatFileSize(undefined), undefined);
});
