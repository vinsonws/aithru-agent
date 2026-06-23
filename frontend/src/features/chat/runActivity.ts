import type { InlineRequest, RunStreamState, TodoEntry, ToolCallEntry } from "./useRunStream";

export type RunActivityItemStatus = "completed" | "current" | "waiting" | "failed" | "next";

export interface RunActivityItem {
  id: string;
  title: string;
  detail?: string;
  status: RunActivityItemStatus;
  source: "todo" | "request" | "tool" | "run";
}

export interface RunActivitySummary {
  status: RunStreamState["status"];
  progress: { done: number; total: number };
  current: RunActivityItem | null;
  items: RunActivityItem[];
  usageLabel: string | null;
  narrative: {
    title: string;
    detail?: string;
    nextAction?: "reply" | "reviewApproval" | "inspectTrace" | "none";
  };
  toolCounts: {
    completed: number;
    failed: number;
    running: number;
  };
}

export interface RunCompanionBadges {
  activity: number;
  files: number;
  approvals: number;
  trace: number;
}

const DONE_STATUSES = new Set(["done", "completed"]);
const ACTIVE_STATUSES = new Set(["in_progress", "running", "active"]);
const WAITING_STATUSES = new Set(["waiting_input", "waiting_approval", "paused"]);
const FILE_TOOL_PATTERNS = [
  "file",
  "workspace",
  "artifact",
  ".ts",
  ".tsx",
  ".py",
  ".md",
  ".json",
  ".txt",
];

export function buildRunActivity(state: RunStreamState): RunActivitySummary {
  const todoItems = state.todos.map(todoToActivityItem);
  const requestItems = state.inlineRequests.map(requestToActivityItem);
  const failedToolItems = state.toolCalls
    .filter((tool) => tool.status === "failed")
    .map(toolToActivityItem);

  const items = [...todoItems, ...requestItems, ...failedToolItems];
  const runItem = runStatusItem(state);
  const current =
    requestItems[0] ??
    failedToolItems[0] ??
    todoItems.find((item) => item.status === "current") ??
    runItem;

  const progressTotal = state.todos.length;
  const progressDone = state.todos.filter((todo) => DONE_STATUSES.has(todo.status)).length;

  const toolCounts = {
    completed: state.toolCalls.filter((t) => t.status === "completed").length,
    failed: state.toolCalls.filter((t) => t.status === "failed").length,
    running: state.toolCalls.filter((t) => t.status === "started" || t.status === "proposed").length,
  };

  return {
    status: state.status,
    progress: { done: progressDone, total: progressTotal },
    current,
    items: items.length > 0 ? items : runItem ? [runItem] : [],
    usageLabel: formatUsage(state.tokenUsage?.total),
    narrative: buildNarrative(state, current),
    toolCounts,
  };
}

function buildNarrative(
  state: RunStreamState,
  current: RunActivityItem | null,
): RunActivitySummary["narrative"] {
  if (state.status === "idle") {
    return { title: "Not started" };
  }
  if (state.status === "running" && state.todos.length === 0 && state.inlineRequests.length === 0) {
    return { title: "Agent is working", nextAction: "none" };
  }
  if (state.status === "waiting_input") {
    const req = state.inlineRequests.find((r) => r.kind === "input");
    return {
      title: req?.prompt ?? "Waiting for your input",
      nextAction: "reply",
    };
  }
  if (state.status === "waiting_approval") {
    return {
      title: "Approval needed",
      detail: current?.detail,
      nextAction: "reviewApproval",
    };
  }
  if (state.status === "failed") {
    return {
      title: current?.title ?? "Run failed",
      detail: current?.detail ?? state.error,
      nextAction: "inspectTrace",
    };
  }
  if (state.status === "completed") {
    const detailParts: string[] = [];
    const fileTools = state.toolCalls.filter(toolLooksFileRelated);
    if (fileTools.length > 0) {
      detailParts.push(`${fileTools.length} file${fileTools.length > 1 ? "s" : ""} changed`);
    }
    if (state.toolCalls.some((t) => t.status === "completed" && !toolLooksFileRelated(t))) {
      detailParts.push(`${state.toolCalls.filter((t) => t.status === "completed").length} actions`);
    }
    return {
      title: "Run completed",
      detail: detailParts.length > 0 ? detailParts.join(" · ") : undefined,
      nextAction: "none",
    };
  }
  if (current) {
    return { title: current.title, detail: current.detail };
  }
  return { title: "Agent is working", nextAction: "none" };
}

export function buildRunCompanionBadges(state: RunStreamState): RunCompanionBadges {
  const approvals = state.inlineRequests.filter((request) =>
    request.kind === "approval" || request.kind === "external_approval"
  ).length;
  const files = state.toolCalls.filter(toolLooksFileRelated).length;
  const trace = state.error || state.toolCalls.some((tool) => tool.status === "failed") ? 1 : 0;
  const activity = state.inlineRequests.length + state.toolCalls.filter((tool) => tool.status === "failed").length;

  return { activity, files, approvals, trace };
}

function todoToActivityItem(todo: TodoEntry): RunActivityItem {
  return {
    id: todo.id,
    title: todo.title || "Untitled step",
    status: todoStatus(todo.status),
    source: "todo",
  };
}

function todoStatus(status: string): RunActivityItemStatus {
  if (DONE_STATUSES.has(status)) return "completed";
  if (ACTIVE_STATUSES.has(status)) return "current";
  if (status === "blocked" || status === "failed") return "failed";
  return "next";
}

function requestToActivityItem(request: InlineRequest): RunActivityItem {
  return {
    id: request.id,
    title: request.prompt || request.toolName || "Agent needs attention",
    detail: request.kind === "input" ? "Reply to continue this run." : "Review this action before the run continues.",
    status: "waiting",
    source: "request",
  };
}

function toolToActivityItem(tool: ToolCallEntry): RunActivityItem {
  return {
    id: tool.id,
    title: tool.toolName,
    detail: tool.error || tool.outputSummary || tool.inputSummary,
    status: tool.status === "failed" ? "failed" : tool.status === "completed" ? "completed" : "current",
    source: "tool",
  };
}

function runStatusItem(state: RunStreamState): RunActivityItem | null {
  if (state.status === "idle") return null;
  if (state.status === "failed") {
    return {
      id: "run-failed",
      title: "Run failed",
      detail: state.error,
      status: "failed",
      source: "run",
    };
  }
  if (WAITING_STATUSES.has(state.status)) {
    return {
      id: "run-waiting",
      title: "Waiting for input",
      status: "waiting",
      source: "run",
    };
  }
  if (state.status === "completed") {
    return {
      id: "run-completed",
      title: "Run completed",
      status: "completed",
      source: "run",
    };
  }
  return {
    id: "run-running",
    title: "Agent is working",
    status: "current",
    source: "run",
  };
}

function formatUsage(total: number | undefined): string | null {
  if (total == null) return null;
  return `${total.toLocaleString("en-US")} tokens`;
}

function toolLooksFileRelated(tool: ToolCallEntry): boolean {
  const haystack = [
    tool.toolName,
    tool.inputSummary,
    tool.outputSummary,
    tool.error,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return FILE_TOOL_PATTERNS.some((pattern) => haystack.includes(pattern));
}
