import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadChatComposerOptions() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/composerState.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("auto mode without a model profile omits harness options", async () => {
  const { buildComposerHarnessOptions } = await loadChatComposerOptions();
  assert.equal(buildComposerHarnessOptions("__default__", "auto"), undefined);
});

test("plan mode adds run instructions and preserves selected model profile", async () => {
  const { buildComposerHarnessOptions } = await loadChatComposerOptions();
  const options = buildComposerHarnessOptions("MiniMax-M2.7", "plan");

  assert.equal(options.model_profile_key, "MiniMax-M2.7");
  assert.match(options.instructions, /Aithru mode: plan/);
});

test("chat mode adds chat instructions", async () => {
  const { buildComposerHarnessOptions } = await loadChatComposerOptions();
  const options = buildComposerHarnessOptions("__default__", "chat");

  assert.match(options.instructions, /Aithru mode: chat/);
});
