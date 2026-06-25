import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunsApiWithCapturedStreamPath(afterSequence) {
  let capturedPath = null;
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/lib/api/runs.ts"],
    plugins: [
      {
        name: "mock-client",
        setup(build) {
          build.onResolve({ filter: /^\.\/client$/ }, () => ({
            path: "mock-client",
            namespace: "mock",
          }));
          build.onLoad({ filter: /.*/, namespace: "mock" }, () => ({
            contents: `
              export function apiRequest() {}
              export function openEventStream(path) {
                globalThis.__capturedRunStreamPath = path;
                return Promise.resolve();
              }
            `,
            loader: "js",
          }));
        },
      },
    ],
  });

  const afterSequenceArg = afterSequence === undefined ? "undefined" : String(afterSequence);
  const code = `${result.outputFiles[0].text}
    await runsApi.stream("run_123", () => {}, undefined, ${afterSequenceArg});
    export default globalThis.__capturedRunStreamPath;
  `;
  const module = await import(`data:text/javascript,${encodeURIComponent(code)}`);
  capturedPath = module.default;
  delete globalThis.__capturedRunStreamPath;
  return capturedPath;
}

test("runsApi.stream follows live run events", async () => {
  assert.equal(
    await loadRunsApiWithCapturedStreamPath(),
    "/api/runs/run_123/stream?follow=true",
  );
});

test("runsApi.stream follows only events after the backfill cursor", async () => {
  assert.equal(
    await loadRunsApiWithCapturedStreamPath(42),
    "/api/runs/run_123/stream?follow=true&after_sequence=42",
  );
});
