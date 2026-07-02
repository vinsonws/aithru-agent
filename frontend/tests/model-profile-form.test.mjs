import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadFormHelpers() {
  const result = await esbuild.build({
    absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["tests/fixtures/model-profile-form.ts"],
  });
  return import(
    `data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`
  );
}

test("deepseek preset creates provider and model payloads", async () => {
  const { deepSeekPresetProvider, deepSeekPresetModels } =
    await loadFormHelpers();
  assert.deepEqual(deepSeekPresetProvider("sk-test"), {
    key: "deepseek",
    name: "DeepSeek",
    kind: "openai_compatible",
    enabled: true,
    base_url: "https://api.deepseek.com",
    compat: "deepseek",
    auth_secret: { write_only_value: "sk-test" },
  });
  assert.deepEqual(
    deepSeekPresetModels().map((model) => model.key),
    ["deepseek-v4-flash", "deepseek-v4-pro"],
  );
});

test("custom provider form builds provider and model payloads", async () => {
  const { buildCustomProviderPayload, buildModelPayload } =
    await loadFormHelpers();
  assert.deepEqual(
    buildCustomProviderPayload({
      key: "my-gateway",
      name: "My Gateway",
      baseUrl: "https://gateway.example/v1",
      apiKey: "sk-test",
    }),
    {
      key: "my-gateway",
      name: "My Gateway",
      kind: "openai_compatible",
      enabled: true,
      base_url: "https://gateway.example/v1",
      compat: null,
      auth_secret: { write_only_value: "sk-test" },
    },
  );
  assert.deepEqual(
    buildModelPayload({
      key: "qwen3-coder",
      name: "Qwen3 Coder",
      providerModelId: "qwen3-coder",
      thinking: true,
      vision: false,
    }),
    {
      key: "qwen3-coder",
      name: "Qwen3 Coder",
      provider_model_id: "qwen3-coder",
      enabled: true,
      capabilities: { thinking: true, vision: false },
    },
  );
});
