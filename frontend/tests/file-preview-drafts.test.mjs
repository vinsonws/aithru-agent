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
  assert.match(source, /srcDoc=/);
  assert.match(source, /enabled: !!activeFile && activeFile\.canPreview && activeFile\.draftContent === undefined/);
});

test("FilePreviewPanel keeps draft HTML iframes script-disabled while persisted HTML previews stay script-enabled", async () => {
  const source = await readFile(filePreviewPanelPath, "utf8");

  assert.match(
    source,
    /if \(preview\.kind === "html" && preview\.content !== undefined\)[\s\S]*?srcDoc=\{preview\.content\}[\s\S]*?sandbox=""/,
  );
  assert.match(
    source,
    /if \(preview\.kind === "html" && preview\.url\)[\s\S]*?src=\{preview\.url\}[\s\S]*?sandbox="allow-scripts"/,
  );
});

test("FileListPanel passes draft workspace files into run file views", async () => {
  const source = await readFile(fileListPanelPath, "utf8");

  assert.match(source, /draftWorkspaceFiles/);
  assert.match(source, /buildRunFileViews\(\{/);
  assert.match(source, /draftWorkspaceFiles,/);
});
