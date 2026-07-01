import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadChatComposerOptions() {
  const result = await esbuild.build({
    absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/composerState.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("thinking mode sends low effort without enabling plan tools", async () => {
  const { buildComposerHarnessOptions } = await loadChatComposerOptions();
  assert.deepEqual(buildComposerHarnessOptions("", "thinking", "thinking"), {
    mode: "thinking",
    thinking_enabled: true,
    is_plan_mode: false,
    subagent_enabled: false,
    model_capabilities: { vision: false, thinking: true },
    model_reasoning_effort: "low",
  });
});

test("pro mode enables plan todo behavior without prompt-only mode instructions", async () => {
  const { buildComposerHarnessOptions } = await loadChatComposerOptions();
  const options = buildComposerHarnessOptions("MiniMax-M2.7", "pro", "pro");

  assert.equal(options.model_profile_key, "MiniMax-M2.7");
  assert.equal(options.mode, "pro");
  assert.equal(options.thinking_enabled, true);
  assert.equal(options.is_plan_mode, true);
  assert.equal(options.subagent_enabled, false);
  assert.equal(options.instructions, undefined);
  assert.deepEqual(options.model_capabilities, { vision: false, thinking: true });
  assert.equal(options.model_reasoning_effort, "medium");
});

test("flash mode disables thinking and plan behavior", async () => {
  const { buildComposerHarnessOptions } = await loadChatComposerOptions();
  const options = buildComposerHarnessOptions("", "flash", "flash");

  assert.equal(options.mode, "flash");
  assert.equal(options.thinking_enabled, false);
  assert.equal(options.is_plan_mode, false);
  assert.equal(options.subagent_enabled, false);
  assert.equal(options.instructions, undefined);
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

  assert.equal(composerModeForReasoningLevel("flash"), "flash");
  assert.equal(composerModeForReasoningLevel("quick"), "flash");
  assert.equal(composerModeForReasoningLevel("thinking"), "thinking");
  assert.equal(composerModeForReasoningLevel("pro"), "pro");
  assert.equal(composerModeForReasoningLevel("ultra"), "ultra");
  assert.equal(reasoningEffortForReasoningLevel("flash"), "none");
  assert.equal(reasoningEffortForReasoningLevel("quick"), "none");
  assert.equal(reasoningEffortForReasoningLevel("thinking"), "low");
  assert.equal(reasoningEffortForReasoningLevel("pro"), "medium");
  assert.equal(reasoningEffortForReasoningLevel("ultra"), "high");
  assert.equal(reasoningLevelForComposerMode("chat"), "flash");
  assert.equal(reasoningLevelForComposerMode("auto"), "thinking");
  assert.equal(reasoningLevelForComposerMode("plan"), "pro");
});

test("buildComposerSummaryParts returns readable defaults", async () => {
  const { buildComposerSummaryParts } = await loadChatComposerOptions();
  assert.deepEqual(
    buildComposerSummaryParts({
      mode: "thinking",
      profileKey: "",
      profileName: null,
      skillId: "__none__",
      skillName: null,
      permissionPolicy: "ask",
    }),
    {
      modeLabelKey: "chat:modeThinking",
      modeFallback: "Thinking",
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
