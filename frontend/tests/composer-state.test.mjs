import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadComposerState() {
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
  const { buildComposerHarnessOptions } = await loadComposerState();
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
  const { buildComposerHarnessOptions } = await loadComposerState();
  const options = buildComposerHarnessOptions("MiniMax-M2.7", "pro", "pro");

  assert.equal(options.model_ref, "MiniMax-M2.7");
  assert.equal(options.mode, "pro");
  assert.equal(options.thinking_enabled, true);
  assert.equal(options.is_plan_mode, true);
  assert.equal(options.subagent_enabled, false);
  assert.equal(options.instructions, undefined);
  assert.deepEqual(options.model_capabilities, { vision: false, thinking: true });
  assert.equal(options.model_reasoning_effort, "medium");
});

test("flash mode disables model thinking and plan behavior", async () => {
  const { buildComposerHarnessOptions } = await loadComposerState();
  const options = buildComposerHarnessOptions("", "flash", "flash");

  assert.equal(options.mode, "flash");
  assert.equal(options.thinking_enabled, false);
  assert.equal(options.is_plan_mode, false);
  assert.equal(options.subagent_enabled, false);
  assert.equal(options.instructions, undefined);
  assert.deepEqual(options.model_capabilities, { vision: false, thinking: false });
  assert.equal(options.model_reasoning_effort, "none");
});

test("reasoning levels map to model reasoning effort", async () => {
  const { reasoningEffortForReasoningLevel } = await loadComposerState();

  assert.equal(reasoningEffortForReasoningLevel("flash"), "none");
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
  assert.ok(scopes.includes("agent.presentation.write"));
  assert.ok(!scopes.includes("agent.artifact.write"));
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

test("provider models flatten to usable model refs", async () => {
  const { flattenUsableModels, selectUsableModelRef } = await loadComposerState();
  const providers = [
    { key: "empty", name: "Empty", enabled: true, models: [] },
    {
      key: "deepseek",
      name: "DeepSeek",
      enabled: true,
      models: [
        {
          key: "deepseek-v4-flash",
          name: "Flash",
          provider_model_id: "deepseek-v4-flash",
          enabled: true,
        },
        { key: "disabled", name: "Disabled", provider_model_id: "disabled", enabled: false },
      ],
    },
    {
      key: "off",
      name: "Off",
      enabled: false,
      models: [{ key: "model", name: "Model", provider_model_id: "model", enabled: true }],
    },
  ];

  assert.deepEqual(flattenUsableModels(providers).map((model) => model.ref), [
    "deepseek/deepseek-v4-flash",
  ]);
  assert.equal(
    selectUsableModelRef(providers, "", "deepseek/deepseek-v4-flash"),
    "deepseek/deepseek-v4-flash",
  );
  assert.equal(
    selectUsableModelRef(providers, "deepseek/deepseek-v4-flash", null),
    "deepseek/deepseek-v4-flash",
  );
  assert.equal(selectUsableModelRef(providers, "missing", null), "");
  assert.equal(selectUsableModelRef(providers, "", "missing/default"), "");
  assert.equal(selectUsableModelRef([], ""), "");
});

test("frontend run harness contract exposes model_ref without legacy profile selection", () => {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const openapi = readFileSync(new URL("../openapi.json", import.meta.url), "utf8");
  const schema = readFileSync(new URL("../src/lib/api/schema.d.ts", import.meta.url), "utf8");
  const legacyKeyPattern = new RegExp('"model_' + 'profile_key"');
  const legacySchemaPattern = new RegExp("model_" + "profile_key\\?: string \\| null;");

  assert.match(openapi, /"model_ref"/);
  assert.doesNotMatch(openapi, legacyKeyPattern);
  assert.match(schema, /model_ref\?: string \| null;/);
  assert.doesNotMatch(schema, legacySchemaPattern);
  assert.ok(root);
});

test("provider compat remains an opaque string contract", () => {
  const openapi = JSON.parse(readFileSync(new URL("../openapi.json", import.meta.url), "utf8"));
  const schema = readFileSync(new URL("../src/lib/api/schema.d.ts", import.meta.url), "utf8");

  assert.equal(openapi.components.schemas.AgentModelCompatKind.type, "string");
  assert.equal(openapi.components.schemas.AgentModelCompatKind.enum, undefined);
  assert.match(schema, /AgentModelCompatKind: string;/);
  assert.doesNotMatch(schema, /AgentModelCompatKind: "deepseek"/);
});
