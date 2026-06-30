import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const removedRunSkillField = ["skill", "id"].join("_");
const removedRunSkillFieldPattern = new RegExp(`${removedRunSkillField}:`);

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

test("chat composer create-run request sends selected skill keys and omits the legacy run skill field", async () => {
  const composer = await src("features/chat/ChatComposer.tsx");
  const requestBody = composer.match(/const body: CreateRunRequest = \{[\s\S]*?\n\s*\};/)?.[0] ?? "";

  assert.match(requestBody, /selected_skill_keys: vars\.selectedSkillKeys/);
  assert.doesNotMatch(requestBody, removedRunSkillFieldPattern);
  assert.match(composer, /selectedSkillKeys:\s*command\.selectedSkillKeys \?\? \[\]/);
});

test("new thread create-run request sends selected skill keys and omits the legacy run skill field", async () => {
  const newThreadPage = await src("features/conversation/NewThreadPage.tsx");
  const requestBody = newThreadPage.match(/const run = await runsApi\.create\(\{[\s\S]*?\n\s*\}\);/)?.[0] ?? "";

  assert.match(requestBody, /selected_skill_keys: vars\.selectedSkillKeys/);
  assert.doesNotMatch(requestBody, removedRunSkillFieldPattern);
  assert.match(newThreadPage, /selectedSkillKeys:\s*command\.selectedSkillKeys \?\? \[\]/);
});

test("creating a run from a run route navigates to the new run stream", async () => {
  const source = await src("AppShell.tsx");

  assert.match(source, /useNavigate/);
  assert.match(source, /navigate\(`\/threads\/\$\{encodeURIComponent\(threadId\)\}\/runs\/\$\{encodeURIComponent\(id\)\}`\)/);
});

test("composer inherits the active run reasoning mode after navigation", async () => {
  const conversation = await src("features/conversation/ConversationPage.tsx");
  const composer = await src("features/chat/ChatComposer.tsx");

  assert.match(conversation, /initialReasoningLevel=\{activeRun \? getRunMode\(activeRun\) : null\}/);
  assert.match(composer, /initialReasoningLevel\?: ComposerReasoningLevel \| null/);
  assert.match(composer, /if \(initialReasoningLevel\) setReasoningLevel\(normalizeReasoningLevel\(initialReasoningLevel\)\)/);
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

test("assistant process reasoning content omits repeated Thinking subheading", async () => {
  const source = await src("features/chat/ChatPanel.tsx");

  assert.doesNotMatch(source, /chat:process\.thinkingLabel/);
  assert.match(source, /<Markdown variant="chat">\{step\.content\}<\/Markdown>/);
});

test("assistant process summary uses per-process timing", async () => {
  const source = await src("features/chat/ChatPanel.tsx");

  assert.match(source, /startedAt:\s*item\.startedAt/);
  assert.match(source, /completedAt:\s*item\.completedAt/);
  assert.doesNotMatch(source, /processDurationLabel\(state,\s*t\)/);
});

test("assistant output fragments only show message footer on the final fragment", async () => {
  const source = await src("features/chat/ChatPanel.tsx");

  assert.match(source, /showFooter = true/);
  assert.match(source, /footerMessage\?: ChatMessage/);
  assert.match(source, /showFooter=\{item\.showFooter \?\? true\}/);
  assert.match(source, /footerMessage=\{item\.footerMessage\}/);
});

test("assistant message text does not render a streaming cursor", async () => {
  const source = await src("features/chat/ChatPanel.tsx");

  assert.doesNotMatch(source, /message\.streaming\s*&&/);
  assert.doesNotMatch(source, /align-text-bottom/);
  assert.doesNotMatch(source, /animate-pulse bg-accent/);
});

test("FileCard renders workspace files in the chat timeline when present", async () => {
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
