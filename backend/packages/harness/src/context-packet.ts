import type { AgentMessage, AgentRun, AgentStreamEvent } from "@aithru-agent/contracts";
import type { AgentContextSummary } from "@aithru-agent/persistence";

export const MODEL_CONTEXT_MESSAGE_LIMIT = 12;
export const MODEL_CONTEXT_CONTENT_LIMIT = 1000;
const MODEL_CONTEXT_TOOL_RESULT_LIMIT = 8;
const PLAN_TODO_CONTEXT = [
  "Todo planning:",
  "Use todo.create and todo.update to track complex multi-step objectives.",
  "Create todos only when the task has multiple concrete steps; keep titles short and actionable.",
  "Keep at most one todo in_progress unless work is genuinely parallel, and mark items completed as soon as they are done.",
  "Agent Todos are runtime harness state, not workflow definitions.",
  "Do not create todos for simple one-step replies.",
].join("\n");

export interface ModelContextPacket {
  messages: AgentMessage[];
  stats: {
    total_messages: number;
    included_messages: number;
    dropped_messages: number;
    truncated_messages: number;
    included_tool_results: number;
    truncated_tool_results: number;
    included_summary: boolean;
    plan_mode: boolean;
    active_skill_keys: string[];
    visible_skill_count: number;
  };
}

export function buildModelContextPacket(args: {
  run: AgentRun;
  messages: AgentMessage[];
  events: AgentStreamEvent[];
  latestSummary?: AgentContextSummary;
  skillInstructions?: Array<{ name: string; instructions: string }>;
  skillCatalog?: Array<{ key: string; name: string; description: string | null }>;
  activeSkillKeys?: string[];
}): ModelContextPacket {
  const included = args.messages.slice(-MODEL_CONTEXT_MESSAGE_LIMIT);
  let truncatedMessages = 0;
  const bounded = included.map((message) => {
    if (message.content.length <= MODEL_CONTEXT_CONTENT_LIMIT) return message;
    truncatedMessages += 1;
    return { ...message, content: message.content.slice(0, MODEL_CONTEXT_CONTENT_LIMIT) };
  });

  let truncatedToolResults = 0;
  const toolLines = args.events
    .filter((event) => event.type === "tool.completed" || event.type === "tool.failed")
    .slice(-MODEL_CONTEXT_TOOL_RESULT_LIMIT)
    .map((event) => {
      const payload = event.payload as Record<string, unknown>;
      const body = payload.error ?? payload.output ?? null;
      const compact = compactValue(body);
      if (compact.endsWith("...")) truncatedToolResults += 1;
      return `- ${String(payload.name ?? "tool")} (${String(payload.tool_call_id ?? event.id)}): ${compact}`;
    });

  const contextParts: string[] = [];
  if (args.skillInstructions?.length) {
    contextParts.push(
      [
        "Active skills:",
        ...args.skillInstructions.map((skill) => `## ${skill.name}\n${skill.instructions}`),
      ].join("\n\n"),
    );
  }
  if (args.skillCatalog?.length) {
    contextParts.push(
      [
        "Available skills:",
        ...args.skillCatalog.map((skill) =>
          `- ${skill.key}: ${skill.name}${skill.description ? ` — ${skill.description}` : ""}`,
        ),
        "Use skill.load with a skill key when a skill's full instructions are needed.",
      ].join("\n"),
    );
  }
  const planMode = isPlanModeRun(args.run);
  if (planMode) contextParts.push(PLAN_TODO_CONTEXT);
  if (args.latestSummary?.summary) contextParts.push(`Context summary:\n${args.latestSummary.summary}`);
  if (toolLines.length) contextParts.push(`Recent tool results:\n${toolLines.join("\n")}`);

  const contextMessages = contextParts.length
    ? [
        {
          id: `ctx_${args.run.id}`,
          thread_id: args.run.thread_id ?? args.run.id,
          role: "system" as const,
          content: contextParts.join("\n\n"),
          run_id: args.run.id,
          workspace_paths: [],
          created_at: new Date().toISOString().replace(/\.\d{3}/, ""),
        },
      ]
    : [];

  return {
    messages: [...contextMessages, ...bounded],
    stats: {
      total_messages: args.messages.length,
      included_messages: bounded.length,
      dropped_messages: Math.max(0, args.messages.length - bounded.length),
      truncated_messages: truncatedMessages,
      included_tool_results: toolLines.length,
      truncated_tool_results: truncatedToolResults,
      included_summary: Boolean(args.latestSummary?.summary),
      plan_mode: planMode,
      active_skill_keys: args.activeSkillKeys ?? [],
      visible_skill_count: args.skillCatalog?.length ?? 0,
    },
  };
}

export function isPlanModeRun(run: AgentRun): boolean {
  const options = run.harness_options;
  if (!options || typeof options !== "object") return false;
  const record = options as Record<string, unknown>;
  if (record.is_plan_mode === true) return true;
  if (record.mode === "pro" || record.mode === "ultra") return true;
  const instructions = typeof record.instructions === "string" ? record.instructions : "";
  return /\[Aithru mode: plan\]/i.test(instructions);
}

function compactValue(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(redact(value));
  if (!text) return "null";
  return text.length > MODEL_CONTEXT_CONTENT_LIMIT
    ? `${text.slice(0, MODEL_CONTEXT_CONTENT_LIMIT)}...`
    : text;
}

function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, child]) => [
      key,
      /token|secret|password|api[_-]?key/i.test(key) ? "[redacted]" : redact(child),
    ]),
  );
}
