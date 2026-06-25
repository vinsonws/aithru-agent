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
  assert.match(source, /chat:inbox\.actions\.open/);
  assert.match(source, /chat:inbox\.actions\.rename/);
  assert.match(source, /chat:inbox\.actions\.delete/);
});

test("conversation header renders localized status without run action buttons", async () => {
  const source = await src("features/conversation/ConversationHeader.tsx");

  assert.match(source, /useTranslation/);
  assert.match(source, /t\(view\.status\.labelKey/);
  assert.doesNotMatch(source, /view\.actions\.map/);
  assert.doesNotMatch(source, /onAction/);
});

test("conversation header renders token usage stat from the active stream", async () => {
  const header = await src("features/conversation/ConversationHeader.tsx");
  const page = await src("features/conversation/ConversationPage.tsx");
  const en = await src("i18n/resources/en/chat.json");
  const zh = await src("i18n/resources/zh/chat.json");

  assert.match(header, /TokenUsageStat/);
  assert.match(header, /chat:usageTooltipTitle/);
  assert.match(header, /onMouseEnter/);
  assert.match(header, /onPointerEnter/);
  assert.match(header, /onFocus/);
  assert.match(header, /onPointerDown/);
  assert.match(header, /preventDefault/);
  assert.doesNotMatch(header, /onClick=\{showDetail\}/);
  assert.match(header, /group-hover:visible/);
  assert.match(header, /group-focus-within:visible/);
  assert.match(header, /role="tooltip"/);
  assert.match(page, /tokenUsage=\{streamState\.tokenUsage\}/);
  assert.match(en, /"usageTooltipTitle": "Token usage"/);
  assert.match(zh, /"usageTooltipTitle": "Token 用量"/);
});

test("templates and file actions use translation keys instead of English fallbacks", async () => {
  const newThread = await src("features/conversation/NewThreadPage.tsx");
  const composer = await src("features/chat/ChatComposer.tsx");
  const fileList = await src("features/sidebar/panels/FileListPanel.tsx");
  const filePreview = await src("features/sidebar/panels/FilePreviewPanel.tsx");
  const messageActions = await src("features/chat/MessageActionsComponent.tsx");

  assert.match(newThread, /t\(template\.titleKey/);
  assert.match(newThread, /t\(template\.descriptionKey/);
  assert.match(composer, /t\(template\.titleKey/);
  assert.match(fileList, /chat:tabFiles/);
  assert.match(filePreview, /chat:tabPreview/);
  assert.match(fileList, /chat:files\.download/);
  assert.match(fileList, /chat:files\.itemCount/);
  assert.match(fileList, /chat:files\.emptyTitle/);
  assert.match(messageActions, /t\(action\.labelKey/);
  assert.match(messageActions, /chat:messageActions\.copied/);
});

test("chat resources expose right panel labels", async () => {
  const content = await src("i18n/resources/en/chat.json");

  assert.match(content, /"tabPreview": "Preview"/);
  assert.match(content, /"tabFiles": "Files"/);
});

test("permission policy and command keys exist in chat resources", async () => {
  const content = await src("i18n/resources/en/chat.json");
  assert.match(content, /"permission":/);
  assert.match(content, /"commandHint":/);
  assert.match(content, /"ask":/);
  assert.match(content, /"autoSafe":/);
  assert.match(content, /"readOnly":/);
});

test("composer renders permission policy selector with i18n keys", async () => {
  const composer = await src("features/chat/ChatComposer.tsx");
  const surface = await src("features/chat/ReferenceComposerSurface.tsx");
  const suggestions = await src("features/chat/composerSuggestions.ts");

  assert.match(surface, /t\(policy\.labelKey/);
  assert.match(surface, /chat:permission\.label/);
  assert.match(suggestions, /chat:slash\.plan\.label/);
  assert.match(composer, /SLASH_SUGGESTIONS/);
});
