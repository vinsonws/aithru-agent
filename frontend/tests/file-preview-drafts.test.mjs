import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const filePreviewPanelPath = new URL(
  "../src/features/sidebar/panels/FilePreviewPanel.tsx",
  import.meta.url,
);
const fileListPanelPath = new URL(
  "../src/features/sidebar/panels/FileListPanel.tsx",
  import.meta.url,
);

test("FilePreviewPanel renders draft previews without workspace fetches", async () => {
  const source = await readFile(filePreviewPanelPath, "utf8");

  assert.match(source, /draftWorkspaceFiles/);
  assert.match(source, /activeFile\.draftContent !== undefined/);
  assert.match(source, /previewFromDraftFile/);
  assert.match(source, /resolveFileViewer/);
  assert.doesNotMatch(source, /srcDoc=/);
  assert.match(source, /enabled: !!activeFile && activeFile\.canPreview && activeFile\.draftContent === undefined/);
});

test("FilePreviewPanel keeps draft HTML source-only while persisted HTML previews stay script-enabled", async () => {
  const source = await readFile(filePreviewPanelPath, "utf8");

  assert.match(source, /if \(preview\.viewer === "source_text"\)/);
  assert.match(
    source,
    /if \(preview\.viewer === "html_preview" && preview\.url\)[\s\S]*?src=\{preview\.url\}[\s\S]*?sandbox="allow-scripts"/,
  );
});

test("FileListPanel passes draft workspace files and presentation hints into run file views", async () => {
  const source = await readFile(fileListPanelPath, "utf8");

  assert.match(source, /draftWorkspaceFiles/);
  assert.match(source, /presentationHints/);
  assert.match(source, /buildRunFileViews\(\{/);
  assert.match(source, /draftWorkspaceFiles,/);
  assert.match(source, /presentationHints,/);
});

test("FilePreviewPanel passes presentation hints into run file views", async () => {
  const source = await readFile(filePreviewPanelPath, "utf8");

  assert.match(source, /presentationHints/);
  assert.match(source, /buildRunFileViews\(\{/);
  assert.match(source, /presentationHints,/);
});

test("FilePreviewPanel includes resolved viewer in preview query key", async () => {
  const source = await readFile(filePreviewPanelPath, "utf8");

  assert.match(source, /const activeViewer =\s*activeFile \? resolveFileViewer\(\{ file: activeFile \}\)\.view : null;/);
  assert.match(source, /queryKey: \["outputs", "preview", workspaceId, activeFile\?\.id, activeFile\?\.previewKind, activeViewer\]/);
});
