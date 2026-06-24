import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const appShellPath = new URL("../src/AppShell.tsx", import.meta.url);

test("inspection companion defaults to collapsed", async () => {
  const source = await readFile(appShellPath, "utf8");

  assert.match(
    source,
    /useLocalStorage\(\s*"aithru-agent:inspection-collapsed",\s*true,\s*\)/,
  );
});
