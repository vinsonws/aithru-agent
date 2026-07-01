import type { AgentMessage, AgentRun } from "@aithru-agent/contracts";
import type { AgentModelAdapter } from "@aithru-agent/model";
import type { AgentStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES, VISIBILITY } from "@aithru-agent/stream";
import { MODEL_CONTEXT_MESSAGE_LIMIT } from "./context-packet.js";

const SUMMARY_MESSAGE_THRESHOLD = MODEL_CONTEXT_MESSAGE_LIMIT + 1;
const SUMMARY_LIMIT = 1000;
const TITLE_MAX_CHARS = 60;
const TITLE_MAX_WORDS = 8;
const TITLE_INSTRUCTIONS =
  "Generate a concise conversation title. Return only the title, no quotes, no markdown.";

export async function runTerminalProcessors(deps: {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  run: AgentRun;
  titleModelAdapter?: AgentModelAdapter;
  phase?: "all" | "before_completion" | "after_completion";
}): Promise<void> {
  if (deps.run.status !== "completed" || !deps.run.thread_id) return;
  const phase = deps.phase ?? "all";
  if (phase !== "after_completion") await safeProcessor(deps, "thread_title", () => maybeGenerateThreadTitle(deps));
  if (phase !== "before_completion") await safeProcessor(deps, "context_summarization", () => maybeCreateContextSummary(deps));
}

async function safeProcessor(
  deps: { store: AgentStore; eventWriter: AgentEventWriter; run: AgentRun },
  processor: string,
  fn: () => void | Promise<void>,
): Promise<void> {
  try {
    await fn();
  } catch (error) {
    deps.eventWriter.write(
      deps.run.id,
      deps.run.thread_id ?? null,
      "runtime.processor.failed",
      {
        hook: "after_terminal",
        processor,
        error: { message: error instanceof Error ? error.message : String(error) },
      },
      { visibility: VISIBILITY.DEBUG, source: { kind: "harness" } },
    );
  }
}

function maybeGenerateThreadTitle(deps: {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  run: AgentRun;
  titleModelAdapter?: AgentModelAdapter;
}): Promise<void> | void {
  const threadId = deps.run.thread_id;
  if (!threadId) return;
  const thread = deps.store.getThread(threadId);
  if (!thread || thread.title?.trim()) return;
  const messages = deps.store.listMessages(threadId);
  return generateThreadTitle(deps, messages).then((generated) => {
    const title = generated ?? deriveThreadTitle(messages, deps.run.task_msg);
    if (!title) return;
    deps.store.updateThread(threadId, {
      title,
      updated_at: new Date().toISOString().replace(/\.\d{3}/, ""),
    });
    deps.eventWriter.write(
      deps.run.id,
      threadId,
      EVENT_TYPES.THREAD_TITLE_GENERATED,
      { thread_id: threadId, title },
      { visibility: VISIBILITY.AUDIT, source: { kind: "harness" } },
    );
  });
}

async function generateThreadTitle(
  deps: { run: AgentRun; titleModelAdapter?: AgentModelAdapter },
  messages: AgentMessage[],
): Promise<string | null> {
  if (!deps.titleModelAdapter) return null;
  const user = messages.find((message) => message.role === "user" && message.content.trim());
  const assistant = messages.find((message) => message.role === "assistant" && message.content.trim());
  if (!user || !assistant) return null;

  const prompt = [
    `Generate a concise title, max ${TITLE_MAX_WORDS} words.`,
    "Return only the title.",
    `User: ${trimForTitlePrompt(user.content)}`,
    `Assistant: ${trimForTitlePrompt(assistant.content)}`,
  ].join("\n");

  let delta = "";
  let completed = "";
  const now = new Date().toISOString().replace(/\.\d{3}/, "");
  for await (const event of deps.titleModelAdapter.createTurn({
    run: {
      ...deps.run,
      task_msg: prompt,
      harness_options: {
        ...(isRecord(deps.run.harness_options) ? deps.run.harness_options : {}),
        instructions: TITLE_INSTRUCTIONS,
        model_reasoning_effort: "none",
      } as AgentRun["harness_options"],
    },
    messages: [{
      id: `msg_${deps.run.id}_title_prompt`,
      thread_id: deps.run.thread_id ?? "",
      role: "user",
      content: prompt,
      run_id: deps.run.id,
      workspace_paths: [],
      created_at: now,
    }],
    context: { purpose: "thread_title" },
    tools: [],
    toolResults: [],
  })) {
    if (event.type === "text_delta") delta += event.delta;
    if (event.type === "completed" && event.content) completed = event.content;
    if (event.type === "failed") return null;
  }
  return cleanTitle(completed || delta);
}

function cleanTitle(value: string): string | null {
  const firstLine = stripThinkingText(value)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
  if (!firstLine) return null;
  let cleaned = firstLine
    .replace(/[#*_`>\[\]()]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[ "'“”‘’]+|[ "'“”‘’.,:;!?，。！？：；]+$/g, "");
  if (!cleaned) return null;
  const words = cleaned.split(/\s+/);
  if (words.length > TITLE_MAX_WORDS) cleaned = words.slice(0, TITLE_MAX_WORDS).join(" ");
  return cleaned.length > TITLE_MAX_CHARS ? `${cleaned.slice(0, TITLE_MAX_CHARS - 3).trim()}...` : cleaned;
}

function trimForTitlePrompt(value: string): string {
  const cleaned = stripThinkingText(value).replace(/\s+/g, " ").trim();
  return cleaned.length > 500 ? `${cleaned.slice(0, 497).trim()}...` : cleaned;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

async function maybeCreateContextSummary(deps: {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  run: AgentRun;
  titleModelAdapter?: AgentModelAdapter;
}): Promise<void> {
  const threadId = deps.run.thread_id;
  if (!threadId) return;
  const messages = deps.store.listMessages(threadId);
  if (messages.length < SUMMARY_MESSAGE_THRESHOLD) return;
  const latest = deps.store.getLatestContextSummary(threadId);
  const summaryCutoff = Math.max(0, messages.length - MODEL_CONTEXT_MESSAGE_LIMIT);
  if (latest && latest.source_message_count >= summaryCutoff) return;
  const summaryMessages = latest
    ? messages.slice(latest.source_message_count, summaryCutoff)
    : messages.slice(0, summaryCutoff);
  if (!summaryMessages.length) return;
  const generated = await generateContextSummary(
    {
      run: deps.run,
      titleModelAdapter: deps.titleModelAdapter,
    },
    summaryMessages,
    latest?.summary,
  );
  const summary = generated ?? deriveContextSummary(messages);
  if (!summary) return;
  deps.store.createContextSummary({
    id: `summary_${deps.run.id}_${summaryCutoff}`,
    org_id: deps.run.org_id,
    thread_id: threadId,
    run_id: deps.run.id,
    summary,
    source_message_count: summaryCutoff,
    created_at: new Date().toISOString().replace(/\.\d{3}/, ""),
  });
  deps.eventWriter.write(
    deps.run.id,
    threadId,
    EVENT_TYPES.CONTEXT_SUMMARY_CREATED,
    { thread_id: threadId, source_message_count: summaryCutoff },
    { visibility: VISIBILITY.AUDIT, source: { kind: "harness" } },
  );
}

async function generateContextSummary(
  deps: { run: AgentRun; titleModelAdapter?: AgentModelAdapter },
  messages: AgentMessage[],
  latestSummary?: string,
): Promise<string | null> {
  if (!deps.titleModelAdapter) return null;

  const prompt = [
    "Update the running conversation summary.",
    "Previous summary:",
    latestSummary?.trim() ? stripThinkingText(latestSummary) : "(none)",
    "New messages to fold in:",
    ...messages.map((message) => `${message.role}: ${trimForSummaryPrompt(message.content)}`),
    "Return only the updated summary.",
  ].join("\n");

  let delta = "";
  let completed = "";
  const now = new Date().toISOString().replace(/\.\d{3}/, "");

  try {
    for await (const event of deps.titleModelAdapter.createTurn({
      run: {
        ...deps.run,
        task_msg: prompt,
        harness_options: {
          ...(isRecord(deps.run.harness_options) ? deps.run.harness_options : {}),
          instructions:
            "Summarize the conversation history using the previous summary and the new messages. Return only the updated summary.",
          model_reasoning_effort: "none",
        } as AgentRun["harness_options"],
      },
      messages: [
        {
          id: `msg_${deps.run.id}_summary_prompt`,
          thread_id: deps.run.thread_id ?? "",
          role: "user",
          content: prompt,
          run_id: deps.run.id,
          workspace_paths: [],
          created_at: now,
        },
      ],
      context: { purpose: "context_summary" },
      tools: [],
      toolResults: [],
    })) {
      if (event.type === "text_delta") delta += event.delta;
      if (event.type === "completed" && event.content) completed = event.content;
      if (event.type === "failed") return null;
    }
  } catch {
    return null;
  }

  return cleanSummary(completed || delta);
}

function deriveThreadTitle(messages: AgentMessage[], fallback: string): string | null {
  const content = messages.find((message) => message.role === "user")?.content ?? fallback;
  const cleaned = stripThinkingText(content)
    .replace(/[#*_`>\[\]()]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return null;
  return cleaned.length > 60 ? `${cleaned.slice(0, 57).trim()}...` : cleaned;
}

function deriveContextSummary(messages: AgentMessage[]): string {
  const text = messages
    .slice(0, -MODEL_CONTEXT_MESSAGE_LIMIT)
    .map((message) => `${message.role}: ${stripThinkingText(message.content)}`)
    .join("\n")
    .replace(/\s+/g, " ")
    .trim();
  return text.length > SUMMARY_LIMIT ? `${text.slice(0, SUMMARY_LIMIT).trim()}...` : text;
}

function trimForSummaryPrompt(value: string): string {
  const cleaned = stripThinkingText(value).replace(/\s+/g, " ").trim();
  return cleaned.length > 500 ? `${cleaned.slice(0, 497).trim()}...` : cleaned;
}

function cleanSummary(value: string): string | null {
  const cleaned = stripThinkingText(value)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n")
    .trim();
  if (!cleaned) return null;
  return cleaned.length > SUMMARY_LIMIT ? `${cleaned.slice(0, SUMMARY_LIMIT).trim()}...` : cleaned;
}

function stripThinkingText(content: string): string {
  return content
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/```(?:thinking|reasoning)[\s\S]*?```/gi, "")
    .trim();
}
