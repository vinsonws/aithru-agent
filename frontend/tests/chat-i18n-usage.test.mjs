import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

async function src(path) {
  return readFile(new URL(`../src/${path}`, import.meta.url), "utf8");
}

test("conversation inbox renders localized search, groups, statuses, and empty states", async () => {
  const source = await src("features/sidebar/ConversationInbox.tsx");

  assert.match(source, /useTranslation/);
  assert.match(source, /chat:inbox\.searchPlaceholder/);
  assert.match(source, /t\(group\.labelKey/);
  assert.match(source, /t\(row\.status\.labelKey/);
  assert.match(source, /chat:inbox\.noMatches/);
});

test("conversation header renders localized status and actions", async () => {
  const source = await src("features/conversation/ConversationHeader.tsx");

  assert.match(source, /useTranslation/);
  assert.match(source, /t\(view\.status\.labelKey/);
  assert.match(source, /t\(action\.labelKey/);
});

test("templates and file actions use translation keys instead of English fallbacks", async () => {
  const newThread = await src("features/conversation/NewThreadPage.tsx");
  const composer = await src("features/chat/ChatComposer.tsx");
  const runFiles = await src("features/inspection/tabs/RunFilesTab.tsx");
  const messageActions = await src("features/chat/MessageActionsComponent.tsx");

  assert.match(newThread, /t\(template\.titleKey/);
  assert.match(newThread, /t\(template\.descriptionKey/);
  assert.match(composer, /t\(template\.titleKey/);
  assert.match(runFiles, /chat:files\.download/);
  assert.doesNotMatch(runFiles, />Download</);
  assert.match(messageActions, /t\(action\.labelKey/);
  assert.match(messageActions, /chat:messageActions\.copied/);
});

test("permission policy and goal bar keys exist in chat resources", async () => {
  const content = await src("i18n/resources/en/chat.json");
  assert.match(content, /"permission":/);
  assert.match(content, /"goalBar":/);
  assert.match(content, /"commandHint":/);
  assert.match(content, /"ask":/);
  assert.match(content, /"autoSafe":/);
  assert.match(content, /"readOnly":/);
});

test("composer renders permission policy selector with i18n keys", async () => {
  const composer = await src("features/chat/ChatComposer.tsx");
  assert.match(composer, /t\(policy\.labelKey/);
  assert.match(composer, /chat:permission\.label/);
  assert.match(composer, /chat:commandHint/);
});
