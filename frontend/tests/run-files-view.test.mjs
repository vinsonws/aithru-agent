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

test("artifacts are listed before workspace files", async () => {
  const { buildRunFileViews } = await loadRunFilesView();
  const views = buildRunFileViews({
    artifacts: [{ id: "a1", name: "report.md", type: "report" }],
    workspaceFiles: [{ path: "src/file.ts", size: 100 }],
  });
  assert.ok(views.length >= 2);
  assert.equal(views[0].kind, "artifact");
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

test("formatFileSize formats bytes correctly", async () => {
  const { formatFileSize } = await loadRunFilesView();
  assert.equal(formatFileSize(0), "0 B");
  assert.equal(formatFileSize(500), "500 B");
  assert.equal(formatFileSize(2048), "2 KB");
  assert.equal(formatFileSize(1048576), "1 MB");
  assert.equal(formatFileSize(null), undefined);
  assert.equal(formatFileSize(undefined), undefined);
});
