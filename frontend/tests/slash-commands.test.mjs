import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadSlashCommands() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/slashCommands.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("/plan with body sends body in plan mode", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/plan Fix login", { activeRunTaskMsg: null }), {
    kind: "send",
    taskMsg: "Fix login",
    modeOverride: "plan",
  });
});

test("/plan without body sets a planning draft", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/plan", { activeRunTaskMsg: null }), {
    kind: "draft",
    draft: "Plan the task before making changes.",
    modeOverride: "plan",
  });
});

test("/status focuses activity instead of creating a run", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/status", { activeRunTaskMsg: "Fix login" }), {
    kind: "local",
    action: "status",
  });
});

test("/retry uses the active run task message when available", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/retry", { activeRunTaskMsg: "Fix login" }), {
    kind: "draft",
    draft: "Retry this task: Fix login",
  });
});

test("/retry without active run task message uses generic retry draft", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/retry", { activeRunTaskMsg: null }), {
    kind: "draft",
    draft: "Retry the last task with the same intent.",
  });
});

test("/clear clears composer locally", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/clear", { activeRunTaskMsg: null }), {
    kind: "local",
    action: "clear",
  });
});

test("unknown slash command is normal text", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/unknown do something", { activeRunTaskMsg: null }), {
    kind: "send",
    taskMsg: "/unknown do something",
  });
});
