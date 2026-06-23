import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadMessageActions() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/messageActions.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

function userMessage(overrides = {}) {
  return { id: "m1", role: "user", content: "Hello agent!", ...overrides };
}

function assistantMessage(overrides = {}) {
  return { id: "m2", role: "assistant", content: "How can I help?", ...overrides };
}

test("user messages expose copy and editAndRerun", async () => {
  const { buildMessageActions } = await loadMessageActions();
  const actions = buildMessageActions(userMessage());
  assert.ok(actions.find((a) => a.kind === "copy"));
  assert.ok(actions.find((a) => a.kind === "editAndRerun"));
  assert.equal(actions.find((a) => a.kind === "continue"), undefined);
});

test("assistant messages expose copy, continue, and viewTrace", async () => {
  const { buildMessageActions } = await loadMessageActions();
  const actions = buildMessageActions(assistantMessage());
  assert.ok(actions.find((a) => a.kind === "copy"));
  assert.ok(actions.find((a) => a.kind === "continue"));
  assert.ok(actions.find((a) => a.kind === "viewTrace"));
});

test("empty messages do not expose copy", async () => {
  const { buildMessageActions } = await loadMessageActions();
  const actions = buildMessageActions(userMessage({ content: "" }));
  assert.equal(actions.find((a) => a.kind === "copy"), undefined);
});

test("streaming assistant messages expose no rerun or trace action", async () => {
  const { buildMessageActions } = await loadMessageActions();
  const actions = buildMessageActions(assistantMessage({ streaming: true }));
  assert.equal(actions.find((a) => a.kind === "editAndRerun"), undefined);
  assert.equal(actions.find((a) => a.kind === "viewTrace"), undefined);
  assert.ok(actions.find((a) => a.kind === "copy"));
});

test("buildEditAndRerunPrompt returns the original user message content", async () => {
  const { buildEditAndRerunPrompt } = await loadMessageActions();
  const prompt = buildEditAndRerunPrompt(userMessage());
  assert.equal(prompt, "Hello agent!");
});

test("buildContinuePrompt includes a short assistant excerpt and asks to continue", async () => {
  const { buildContinuePrompt } = await loadMessageActions();
  const prompt = buildContinuePrompt(assistantMessage({ content: "Here is a long response with lots of details." }));
  assert.match(prompt, /[Cc]ontinue/);
  assert.match(prompt, /Here is a long/);
});
