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
  assert.deepEqual(buildComposerHarnessOptions("", "auto", "thinking"), {
    model_capabilities: { vision: false, thinking: true },
    model_reasoning_effort: "low",
  });
});

test("plan mode adds run instructions and preserves selected model profile", async () => {
  const { buildComposerHarnessOptions } = await loadChatComposerOptions();
  const options = buildComposerHarnessOptions("MiniMax-M2.7", "plan", "pro");

  assert.equal(options.model_profile_key, "MiniMax-M2.7");
  assert.match(options.instructions, /Aithru mode: plan/);
  assert.deepEqual(options.model_capabilities, { vision: false, thinking: true });
  assert.equal(options.model_reasoning_effort, "medium");
});

test("chat mode adds chat instructions", async () => {
  const { buildComposerHarnessOptions } = await loadChatComposerOptions();
  const options = buildComposerHarnessOptions("", "chat", "quick");

  assert.match(options.instructions, /Aithru mode: chat/);
  assert.deepEqual(options.model_capabilities, { vision: false, thinking: false });
  assert.equal(options.model_reasoning_effort, "none");
});

test("reasoning levels map to supported composer modes", async () => {
  const {
    composerModeForReasoningLevel,
    reasoningEffortForReasoningLevel,
    reasoningLevelForComposerMode,
  } =
    await loadChatComposerOptions();

  assert.equal(composerModeForReasoningLevel("quick"), "chat");
  assert.equal(composerModeForReasoningLevel("thinking"), "auto");
  assert.equal(composerModeForReasoningLevel("pro"), "plan");
  assert.equal(composerModeForReasoningLevel("ultra"), "plan");
  assert.equal(reasoningEffortForReasoningLevel("quick"), "none");
  assert.equal(reasoningEffortForReasoningLevel("thinking"), "low");
  assert.equal(reasoningEffortForReasoningLevel("pro"), "medium");
  assert.equal(reasoningEffortForReasoningLevel("ultra"), "high");
  assert.equal(reasoningLevelForComposerMode("chat"), "quick");
  assert.equal(reasoningLevelForComposerMode("auto"), "thinking");
  assert.equal(reasoningLevelForComposerMode("plan"), "pro");
});

test("buildComposerSummaryParts returns readable defaults", async () => {
  const { buildComposerSummaryParts } = await loadChatComposerOptions();
  assert.deepEqual(
    buildComposerSummaryParts({
      mode: "auto",
      profileKey: "",
      profileName: null,
      skillId: "__none__",
      skillName: null,
      permissionPolicy: "ask",
    }),
    {
      modeLabelKey: "chat:modeAuto",
      modeFallback: "Auto",
      modelLabel: "No model",
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
      modelLabel: "gpt-4o-mini",
      skillLabel: null,
      permissionLabel: "Ask",
    }),
    "Auto / gpt-4o-mini / Ask",
  );
});
