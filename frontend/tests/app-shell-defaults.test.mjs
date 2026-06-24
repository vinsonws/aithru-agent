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
});
