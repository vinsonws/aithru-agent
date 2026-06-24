import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

test("host locale sync happens after render, not inside render memoization", async () => {
  const source = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");

  assert.equal(
    source.includes("React.useMemo(() => initI18n(context.locale.language)"),
    false,
  );
  assert.match(source, /React\.useEffect\(\(\) => \{[\s\S]*changeLanguage/);
});
