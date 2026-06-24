import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadFormHelpers() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["tests/fixtures/model-profile-form.ts"],
  });
  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("model profile form sends provider key as a write-only secret", async () => {
  const { buildModelProfileCreatePayload } = await loadFormHelpers();

  assert.deepEqual(
    buildModelProfileCreatePayload({
      key: "fast",
      name: "Fast model",
      provider: "openai",
      model: "gpt-4o-mini",
      apiKey: "  sk-test-secret  ",
      baseUrl: "",
      vision: true,
      thinking: false,
      maxTotalTokens: "200000",
      maxRunCostUsd: "1.5",
    }),
    {
      key: "fast",
      name: "Fast model",
      provider: "openai",
      model: "openai:gpt-4o-mini",
      enabled: true,
      capabilities: { vision: true, thinking: false },
      cost_policy: { max_run_cost_usd: 1.5 },
      selection_policy: { required_scopes: [], max_total_tokens: 200000 },
      auth_secret: { write_only_value: "sk-test-secret" },
    },
  );
});

test("model profile form keeps custom base URLs in metadata", async () => {
  const { buildModelProfileCreatePayload } = await loadFormHelpers();

  assert.deepEqual(
    buildModelProfileCreatePayload({
      key: "local",
      name: "Local model",
      provider: "custom",
      model: "qwen3:32b",
      apiKey: "",
      baseUrl: " http://127.0.0.1:11434/v1 ",
      vision: false,
      thinking: true,
      maxTotalTokens: "",
      maxRunCostUsd: "",
    }),
    {
      key: "local",
      name: "Local model",
      provider: "custom",
      model: "custom:qwen3:32b",
      enabled: true,
      capabilities: { vision: false, thinking: true },
      cost_policy: {},
      selection_policy: { required_scopes: [] },
      metadata: { base_url: "http://127.0.0.1:11434/v1" },
    },
  );
});

test("model profile form infers display name and profile key", async () => {
  const { buildModelProfileCreatePayload } = await loadFormHelpers();

  assert.deepEqual(
    buildModelProfileCreatePayload({
      key: "",
      name: "",
      provider: "anthropic",
      model: "claude-3-5-sonnet-latest",
      apiKey: " sk-ant-test ",
      baseUrl: "",
      vision: true,
      thinking: true,
      maxTotalTokens: "",
      maxRunCostUsd: "",
    }),
    {
      key: "anthropic-claude-3-5-sonnet-latest",
      name: "Claude 3 5 Sonnet Latest",
      provider: "anthropic",
      model: "anthropic:claude-3-5-sonnet-latest",
      enabled: true,
      capabilities: { vision: true, thinking: true },
      cost_policy: {},
      selection_policy: { required_scopes: [] },
      auth_secret: { write_only_value: "sk-ant-test" },
    },
  );
});

test("model profile form preloads existing values for editing", async () => {
  const { modelProfileFormValuesFromProfile } = await loadFormHelpers();

  assert.deepEqual(
    modelProfileFormValuesFromProfile({
      key: "custom-deepseek-v4-flash",
      name: "DeepSeek V4 Flash",
      provider: "custom",
      model: "custom:deepseek-v4-flash",
      enabled: true,
      capabilities: { vision: false, thinking: true },
      cost_policy: { max_run_cost_usd: 2 },
      selection_policy: { required_scopes: ["agent.model.deepseek"], max_total_tokens: 128000 },
      metadata: { base_url: "https://api.deepseek.com/v1", owner: "user" },
      auth_secret: { has_secret: true, redacted: true, secret_ref: "secret://model-profiles/org/custom/api-key" },
      id: "model_profile_1",
      org_id: "org_1",
      created_at: "2026-06-24T00:00:00Z",
      updated_at: "2026-06-24T00:00:00Z",
    }),
    {
      key: "custom-deepseek-v4-flash",
      name: "DeepSeek V4 Flash",
      provider: "custom",
      model: "custom:deepseek-v4-flash",
      apiKey: "",
      baseUrl: "https://api.deepseek.com/v1",
      vision: false,
      thinking: true,
      maxTotalTokens: "128000",
      maxRunCostUsd: "2",
    },
  );
});

test("model profile update preserves unmanaged fields and omits blank api keys", async () => {
  const { buildModelProfileUpdatePayload } = await loadFormHelpers();
  const originalProfile = {
    key: "custom-deepseek-v4-flash",
    name: "DeepSeek V4 Flash",
    provider: "custom",
    model: "custom:deepseek-v4-flash",
    enabled: true,
    capabilities: { vision: false, thinking: false },
    cost_policy: {
      input_cost_per_million_tokens_usd: 0.2,
      output_cost_per_million_tokens_usd: 0.4,
      max_run_cost_usd: 1,
    },
    selection_policy: { required_scopes: ["agent.model.deepseek"], max_total_tokens: 64000 },
    metadata: { base_url: "https://api.deepseek.com/v1", owner: "user" },
    auth_secret: { has_secret: true, redacted: true, secret_ref: "secret://model-profiles/org/custom/api-key" },
    id: "model_profile_1",
    org_id: "org_1",
    created_at: "2026-06-24T00:00:00Z",
    updated_at: "2026-06-24T00:00:00Z",
  };

  assert.deepEqual(
    buildModelProfileUpdatePayload(
      {
        key: "custom-deepseek-v4-flash",
        name: "DeepSeek V4 Flash Updated",
        provider: "custom",
        model: "deepseek-v4-flash",
        apiKey: "",
        baseUrl: "https://api.deepseek.com/v1",
        vision: true,
        thinking: true,
        maxTotalTokens: "128000",
        maxRunCostUsd: "2",
      },
      originalProfile,
    ),
    {
      name: "DeepSeek V4 Flash Updated",
      provider: "custom",
      model: "custom:deepseek-v4-flash",
      capabilities: { vision: true, thinking: true },
      cost_policy: {
        input_cost_per_million_tokens_usd: 0.2,
        output_cost_per_million_tokens_usd: 0.4,
        max_run_cost_usd: 2,
      },
      selection_policy: {
        required_scopes: ["agent.model.deepseek"],
        max_total_tokens: 128000,
      },
      metadata: { base_url: "https://api.deepseek.com/v1", owner: "user" },
    },
  );
});

test("settings model profiles page exposes editing through patch", async () => {
  const source = await import("node:fs/promises").then((fs) =>
    fs.readFile(new URL("../src/features/admin/ModelProfilesPage.tsx", import.meta.url), "utf8"),
  );

  assert.match(source, /modelProfilesApi\.patch/);
  assert.match(source, /editingProfileKey/);
  assert.match(source, /editProfile/);
});
