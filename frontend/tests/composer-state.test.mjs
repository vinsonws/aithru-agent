import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadComposerState() {
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
  const { buildComposerHarnessOptions } = await loadComposerState();
  assert.deepEqual(buildComposerHarnessOptions("", "auto", "thinking"), {
    model_capabilities: { vision: false, thinking: true },
    model_reasoning_effort: "low",
  });
});

test("plan mode adds instructions, profile, and reasoning effort", async () => {
  const { buildComposerHarnessOptions } = await loadComposerState();
  const options = buildComposerHarnessOptions("MiniMax-M2.7", "plan", "pro");

  assert.equal(options.model_profile_key, "MiniMax-M2.7");
  assert.match(options.instructions, /Aithru mode: plan/);
  assert.deepEqual(options.model_capabilities, { vision: false, thinking: true });
  assert.equal(options.model_reasoning_effort, "medium");
});

test("chat mode disables model thinking for quick reasoning", async () => {
  const { buildComposerHarnessOptions } = await loadComposerState();
  const options = buildComposerHarnessOptions("", "chat", "quick");

  assert.match(options.instructions, /Aithru mode: chat/);
  assert.deepEqual(options.model_capabilities, { vision: false, thinking: false });
  assert.equal(options.model_reasoning_effort, "none");
});

test("reasoning levels map to model reasoning effort", async () => {
  const { reasoningEffortForReasoningLevel } = await loadComposerState();

  assert.equal(reasoningEffortForReasoningLevel("quick"), "none");
  assert.equal(reasoningEffortForReasoningLevel("thinking"), "low");
  assert.equal(reasoningEffortForReasoningLevel("pro"), "medium");
  assert.equal(reasoningEffortForReasoningLevel("ultra"), "high");
});

test("read only permission policy grants only read-oriented scopes", async () => {
  const { buildComposerScopes } = await loadComposerState();
  assert.deepEqual(buildComposerScopes("read_only"), [
    "agent.workspace.read",
    "agent.memory.read",
  ]);
});

test("ask permission policy grants common task scopes without wildcard", async () => {
  const { buildComposerScopes } = await loadComposerState();
  const scopes = buildComposerScopes("ask");

  assert.ok(scopes.includes("agent.workspace.read"));
  assert.ok(scopes.includes("agent.workspace.write"));
  assert.ok(scopes.includes("agent.todo.write"));
  assert.ok(scopes.includes("agent.artifact.write"));
  assert.ok(scopes.includes("agent.input.write"));
  assert.ok(!scopes.includes("*"));
});

test("auto safe permission policy uses wildcard scope for trusted local runs", async () => {
  const { buildComposerScopes } = await loadComposerState();
  assert.deepEqual(buildComposerScopes("auto_safe"), ["*"]);
});

test("permission policy can be inferred from persisted run scopes", async () => {
  const { inferPermissionPolicyFromScopes } = await loadComposerState();

  assert.equal(inferPermissionPolicyFromScopes(["*"]), "auto_safe");
  assert.equal(
    inferPermissionPolicyFromScopes(["agent.workspace.read", "agent.memory.read"]),
    "read_only",
  );
  assert.equal(
    inferPermissionPolicyFromScopes(["agent.workspace.read", "agent.workspace.write"]),
    "ask",
  );
});

test("unknown permission policy falls back to ask", async () => {
  const { normalizePermissionPolicyId } = await loadComposerState();
  assert.equal(normalizePermissionPolicyId("bad-value"), "ask");
  assert.equal(normalizePermissionPolicyId(null), "ask");
});
