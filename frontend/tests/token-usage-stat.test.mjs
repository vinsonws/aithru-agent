import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadTokenUsageStat() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/conversation/tokenUsageStat.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("buildTokenUsageDisplay formats compact total and readable detail counters", async () => {
  const { buildTokenUsageDisplay } = await loadTokenUsageStat();

  const display = buildTokenUsageDisplay({ input: 84_400, output: 5_044 });

  assert.deepEqual(display, {
    summary: "89.4K",
    input: "84.4K",
    output: "5,044",
    total: "89.4K",
  });
});

test("buildTokenUsageDisplay hides the stat when no token counters are known", async () => {
  const { buildTokenUsageDisplay } = await loadTokenUsageStat();

  assert.equal(buildTokenUsageDisplay(undefined), null);
  assert.equal(buildTokenUsageDisplay({}), null);
});
