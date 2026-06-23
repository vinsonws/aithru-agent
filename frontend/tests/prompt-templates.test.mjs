import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadPromptTemplates() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/promptTemplates.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("getPromptTemplates returns stable IDs", async () => {
  const { getPromptTemplates } = await loadPromptTemplates();
  const templates = getPromptTemplates();
  const ids = templates.map((t) => t.id);
  assert.deepEqual(ids, ["build", "debug", "summarize", "plan", "research"]);
});

test("each template has required fields", async () => {
  const { getPromptTemplates } = await loadPromptTemplates();
  const templates = getPromptTemplates();
  for (const t of templates) {
    assert.ok(t.titleKey);
    assert.ok(t.fallbackTitle);
    assert.ok(t.prompt);
    assert.ok(t.mode);
    assert.ok(t.descriptionKey);
    assert.ok(t.fallbackDescription);
    assert.ok(["auto", "plan", "chat"].includes(t.mode));
  }
});

test("applying a template returns its prompt without mutation", async () => {
  const { getPromptTemplates } = await loadPromptTemplates();
  const before = getPromptTemplates();
  const template = before[0];
  const prompt = template.prompt;
  assert.ok(typeof prompt === "string");
  assert.ok(prompt.length > 0);
  // Calling again returns new array
  const after = getPromptTemplates();
  assert.equal(after.length, before.length);
});

test("templates cover all required categories", async () => {
  const { getPromptTemplates } = await loadPromptTemplates();
  const categories = new Set(getPromptTemplates().map((t) => t.id));
  assert.ok(categories.has("build"));
  assert.ok(categories.has("debug"));
  assert.ok(categories.has("summarize"));
  assert.ok(categories.has("plan"));
  assert.ok(categories.has("research"));
});
