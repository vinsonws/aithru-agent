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

test("artifacts are listed before modified files", async () => {
  const { buildRunFileViews } = await loadRunFilesView();
  const views = buildRunFileViews({
    artifacts: [{ id: "a1", name: "report.md", type: "report" }],
    workspaceFiles: [{ path: "src/file.ts", size: 100 }],
  });
  assert.ok(views.length >= 2);
  assert.equal(views[0].kind, "artifact");
  assert.equal(views[0].href, "/api/artifacts/a1/download");
  assert.equal(views[0].previewHref, "/api/artifacts/a1/content");
  assert.equal(views[0].artifactId, "a1");
});

test("modified files promoted as artifacts are not duplicated", async () => {
  const { buildRunFileViews } = await loadRunFilesView();
  const views = buildRunFileViews({
    artifacts: [
      {
        id: "a1",
        name: "report.md",
        type: "report",
        metadata: { source_path: "reports/report.md" },
      },
    ],
    workspaceFiles: [
      { path: "reports/report.md", size: 100 },
      { path: "notes/raw.txt", size: 50 },
    ],
  });

  assert.deepEqual(
    views.map((view) => [view.kind, view.path]),
    [
      ["artifact", "reports/report.md"],
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
  assert.equal(previewKindForFile({ name: "final", artifactType: "report" }), "markdown");
  assert.equal(previewKindForFile({ name: "archive.zip" }), "unsupported");
  assert.equal(languageForFile("main.py"), "python");
  assert.equal(languageForFile("component.tsx"), "typescript");
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
