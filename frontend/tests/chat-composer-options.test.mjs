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

test("buildComposerSummaryParts returns readable defaults", async () => {
  const { buildComposerSummaryParts } = await loadChatComposerOptions();
  assert.deepEqual(
    buildComposerSummaryParts({
      mode: "auto",
      profileKey: "__default__",
      profileName: null,
      skillId: "__none__",
      skillName: null,
      permissionPolicy: "ask",
    }),
    {
      modeLabelKey: "chat:modeAuto",
      modeFallback: "Auto",
      modelLabel: "Default model",
      skillLabel: null,
      permissionLabelKey: "chat:permission.ask",
      permissionFallback: "Ask",
    },
  );
});

test("buildComposerSummaryLabel joins mode, model, skill, and permission", async () => {
  const { buildComposerSummaryLabel } = await loadChatComposerOptions();
  assert.equal(
    buildComposerSummaryLabel({
      modeLabel: "Plan",
      modelLabel: "MiniMax",
      skillLabel: "Research",
      permissionLabel: "Read-only",
    }),
    "Plan / MiniMax / Research / Read-only",
  );
});

test("buildComposerSummaryLabel omits empty skill", async () => {
  const { buildComposerSummaryLabel } = await loadChatComposerOptions();
  assert.equal(
    buildComposerSummaryLabel({
      modeLabel: "Auto",
      modelLabel: "Default model",
      skillLabel: null,
      permissionLabel: "Ask",
    }),
    "Auto / Default model / Ask",
  );
});
