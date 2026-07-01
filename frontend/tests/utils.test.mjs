import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadUtils() {
  const result = await esbuild.build({
    absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/lib/utils.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("relativeTime uses past and future directions correctly", async () => {
  const originalNow = Date.now;
  Date.now = () => Date.parse("2026-06-24T04:00:00.000Z");
  try {
    const { relativeTime } = await loadUtils();
    assert.equal(relativeTime("2026-06-24T03:59:00.000Z", "en-US"), "1 minute ago");
    assert.equal(relativeTime("2026-06-24T04:01:00.000Z", "en-US"), "in 1 minute");
  } finally {
    Date.now = originalNow;
  }
});
