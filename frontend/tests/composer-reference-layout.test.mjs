import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

async function src(path) {
  return readFile(new URL(`../src/${path}`, import.meta.url), "utf8");
}

test("composer uses a compact reference shell without a divider", async () => {
  const source = await src("features/chat/ChatComposer.tsx");
  const surface = await src("features/chat/ReferenceComposerSurface.tsx");

  assert.match(source, /max-w-\[46rem\]/);
  assert.doesNotMatch(source, /max-w-5xl/);
  assert.doesNotMatch(source, /border-t/);
  assert.match(source, /ReferenceComposerSurface/);
  assert.match(surface, /rounded-\[1\.75rem\]/);
  assert.match(surface, /min-h-\[76px\]/);
  assert.doesNotMatch(surface, /min-h-\[108px\]/);
  assert.match(surface, /rounded-full/);
  assert.match(surface, /sm:flex-row/);
});

test("new thread input uses the same compact surface size with stamps below it", async () => {
  const source = await src("features/conversation/NewThreadPage.tsx");

  assert.match(source, /max-w-\[46rem\]/);
  assert.doesNotMatch(source, /max-w-5xl/);
  assert.match(source, /justify-center/);
  assert.match(source, /ReferenceComposerSurface/);
  assert.doesNotMatch(source, /min-h-\[132px\]/);
  assert.doesNotMatch(source, /rows=\{4\}/);
  assert.match(source, /rounded-full/);
  assert.match(source, /overflow-x-hidden/);
  assert.match(source, /chat:taskMsgPlaceholder/);
  assert.ok(source.indexOf("<ReferenceComposerSurface") < source.indexOf('data-testid="template-stamp"'));
});

test("composer placeholder copy matches the calmer reference prompt", async () => {
  const en = await src("i18n/resources/en/chat.json");
  const zh = await src("i18n/resources/zh/chat.json");

  assert.match(en, /"taskMsgPlaceholder": "What can Aithru do for you today\?"/);
  assert.match(zh, /"taskMsgPlaceholder": "今天我能为你做些什么？"/);
});

test("composer configuration moved into top menus without skill or at controls", async () => {
  const composer = await src("features/chat/ChatComposer.tsx");
  const surface = await src("features/chat/ReferenceComposerSurface.tsx");

  assert.doesNotMatch(composer, /AtSign/);
  assert.doesNotMatch(composer, /skillsApi/);
  assert.match(surface, /data-testid="reference-composer-permission"/);
  assert.match(surface, /data-testid="reference-composer-model-reasoning"/);
  assert.match(surface, /side="top"/);
  assert.match(surface, /REASONING_LEVELS/);
});

test("slash suggestions render above the input surface", async () => {
  const surface = await src("features/chat/ReferenceComposerSurface.tsx");

  assert.match(surface, /data-testid="slash-suggestions-panel"/);
  assert.match(surface, /bottom-\[calc\(100%\+0\.625rem\)\]/);
});
