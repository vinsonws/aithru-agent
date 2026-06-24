import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

async function src(path) {
  return readFile(new URL(`../src/${path}`, import.meta.url), "utf8");
}

test("chat panel renders avatarless assistant process instead of activity cards", async () => {
  const source = await src("features/chat/ChatPanel.tsx");

  assert.doesNotMatch(source, /import \{[^}]*Bot/);
  assert.doesNotMatch(source, /import \{[^}]*User/);
  assert.doesNotMatch(source, /AgentActivityCard/);
  assert.match(source, /item\.kind === "assistantProcess"/);
  assert.match(source, /AssistantProcess/);
  assert.match(source, /RunCompletionFooter/);
});

test("tool calls are rendered as compact inline rows in the conversation flow", async () => {
  const source = await src("features/chat/ToolCallCard.tsx");

  assert.match(source, /data-testid="tool-call-row"/);
  assert.doesNotMatch(source, /rounded-md border bg-muted\/25 text-sm shadow-none/);
  assert.match(source, /font-mono/);
});

test("chat panel uses a narrower reading rail with lightweight message separation", async () => {
  const source = await src("features/chat/ChatPanel.tsx");

  assert.match(source, /max-w-\[46rem\]/);
  assert.match(source, /border-l border-border\/70 pl-4/);
  assert.doesNotMatch(source, /max-w-5xl/);
  assert.doesNotMatch(source, /56rem/);
});

test("historical assistant process state is display-only and not part of new run payloads", async () => {
  const conversation = await src("features/conversation/ConversationPage.tsx");
  const composer = await src("features/chat/ChatComposer.tsx");
  const requestBody = composer.match(/const body: CreateRunRequest = \{[\s\S]*?\n\s*\};/)?.[0] ?? "";

  assert.match(conversation, /buildRunStreamState\(await runsApi\.events\(runId\)\)/);
  assert.match(conversation, /historicalRunStates=\{historicalRunStatesQuery\.data \?\? \{\}\}/);
  assert.match(requestBody, /task_msg: vars\.taskMsg/);
  assert.match(requestBody, /thread_id: threadId/);
  assert.doesNotMatch(requestBody, /historicalRunStates|threadMessages|streamState|reasoningSegments|toolCalls/);
});

test("assistant process auto-expands while thinking and auto-collapses when final output starts", async () => {
  const source = await src("features/chat/ChatPanel.tsx");

  assert.match(source, /function shouldAutoOpenAssistantProcess/);
  assert.match(source, /hasReasoningContent[\s\S]*reasoningSegments/);
  assert.match(source, /hasAssistantOutput[\s\S]*message\.role === "assistant"/);
  assert.match(source, /!isTerminalState\(item\.state\)/);
  assert.match(source, /!hasAssistantOutput/);
  assert.match(source, /const \[manualOpen, setManualOpen\] = React\.useState<boolean \| null>\(null\)/);
  assert.match(source, /const open = manualOpen \?\? autoOpen/);
});

test("FileCard renders artifact files in the chat timeline when present", async () => {
  const fileCardSource = await src("features/chat/FileCard.tsx");

  // FileCard component exports a function that accepts file and onPreview props
  assert.match(fileCardSource, /export function FileCard/);
  assert.match(fileCardSource, /interface FileCardProps/);
  assert.match(fileCardSource, /file: RunFileView/);
  assert.match(fileCardSource, /onPreview:.*void/);

  // It renders a preview button when the file can be previewed
  assert.match(fileCardSource, /file\.canPreview/);
  assert.match(fileCardSource, /onClick=\{onPreview\}/);

  // It shows the file name and type label
  assert.match(fileCardSource, /file\.name/);
  assert.match(fileCardSource, /file\.typeLabel/);

  // FileCard imports from inspection/runFilesView for RunFileView type
  assert.match(fileCardSource, /@\/features\/inspection\/runFilesView/);
});
