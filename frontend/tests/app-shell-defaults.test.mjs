import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const appShellPath = new URL("../src/AppShell.tsx", import.meta.url);

test("right panel and selected file are session-only React state, not localStorage", async () => {
  const source = await readFile(appShellPath, "utf8");

  // No inspection localStorage keys — replaced with React.useState for session-only state
  assert.doesNotMatch(
    source,
    /aithru-agent:inspection-collapsed/,
  );
  assert.doesNotMatch(
    source,
    /aithru-agent:inspection-tab/,
  );
  assert.match(source, /React\.useState/);

  // rightPanel defaults to null
  assert.match(
    source,
    /rightPanel[^;]*React\.useState<string\s*\|\s*null\s*>\s*\(null\)/,
  );

  // openFileIds defaults to empty array
  assert.match(
    source,
    /openFileIds[^;]*React\.useState<string\[\]>\s*\(\[\]\)/,
  );

  // activeFileId defaults to null
  assert.match(
    source,
    /activeFileId[^;]*React\.useState<string\s*\|\s*null\s*>\s*\(null\)/,
  );
});
