import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { runsApi } from "@/lib/api";
import type { AgentRunStatus, AgentStreamEvent } from "@/lib/api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  runId?: string | null;
  /** Streaming text accumulated from message.delta events. */
  streaming?: boolean;
  sequence?: number;
  lastSequence?: number;
  completedSequence?: number;
  createdAt?: string;
  updatedAt?: string;
  completedAt?: string;
  attachments?: Array<{ name: string; type?: string }>;
}

export interface ToolCallEntry {
  id: string;
  toolName: string;
  status: "proposed" | "started" | "completed" | "failed" | "denied";
  riskLevel?: string;
  inputSummary?: string;
  outputSummary?: string;
  error?: string;
  approvalPolicy?: string;
  messageId?: string;
  sequence?: number;
  lastSequence?: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface ToolInputDraft {
  inputStreamId: string;
  toolCallId?: string;
  toolName?: string;
  inputText: string;
  status: "streaming" | "proposed" | "completed" | "failed" | "denied";
  sequence?: number;
  lastSequence?: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface ReasoningSegment {
  id: string;
  content: string;
  streaming?: boolean;
  sequence?: number;
  lastSequence?: number;
  createdAt?: string;
  updatedAt?: string;
  completedAt?: string;
}

export interface TodoEntry {
  id: string;
  title: string;
  status: string;
  sequence?: number;
}

export interface PresentationEntry {
  id: string;
  status: "pending" | "ready" | "failed" | "dismissed";
  priority: "low" | "normal" | "high";
  title: string;
  summary?: string;
  reason?: string;
  resource: {
    kind: "workspace_file" | "approval" | "todo" | "run" | "trace_span" | "external_url" | "none";
    id?: string;
    path?: string;
    url?: string;
  };
  surfaces: Array<"conversation" | "side_panel" | "approval_panel" | "activity" | "header">;
  preferredView: "html_preview" | "source_text" | "markdown" | "json" | "image" | "pdf" | "diff" | "approval_review" | "activity_detail" | "download" | "open_external" | "none";
  availableViews: PresentationEntry["preferredView"][];
  effects?: Array<{
    kind: "open_panel" | "focus_presentation" | "scroll_to" | "highlight" | "none";
    panel?: string;
    surface?: PresentationEntry["surfaces"][number];
    presentationId?: string;
    mode?: "soft" | "assertive";
  }>;
  actions?: Array<{
    kind: "open_view" | "download" | "approve" | "reject" | "retry" | "continue" | "open_in_workbench" | "open_external" | "copy_reference" | "none";
    label?: string;
    view?: PresentationEntry["preferredView"];
    path?: string;
    method?: "GET" | "POST";
    requiresConfirmation?: boolean;
  }>;
  sequence?: number;
  lastSequence?: number;
  createdAt?: string;
  updatedAt?: string;
  metadata?: Record<string, unknown>;
}

export interface InlineRequest {
  kind: "input" | "approval" | "external_approval" | "external_run";
  id: string;
  prompt?: string;
  approvalId?: string;
  toolName?: string;
  options?: string[];
  runId: string;
  sequence?: number;
  createdAt?: string;
}

export interface RunStreamState {
  status: AgentRunStatus | "idle";
  messages: ChatMessage[];
  toolCalls: ToolCallEntry[];
  toolInputDrafts: ToolInputDraft[];
  reasoningSegments: ReasoningSegment[];
  assistantOutputSegments: ChatMessage[];
  todos: TodoEntry[];
  inlineRequests: InlineRequest[];
  presentations: PresentationEntry[];
  tokenUsage?: { input?: number; output?: number; total?: number };
  error?: string;
  runStartedSequence?: number;
  runStartedAt?: string;
  modelStartedSequence?: number;
  modelStartedAt?: string;
  modelCompletedSequence?: number;
  modelCompletedAt?: string;
  runCompletedSequence?: number;
  runCompletedAt?: string;
  lastEventSequence?: number;
}

const initialState: RunStreamState = {
  status: "idle",
  messages: [],
  toolCalls: [],
  toolInputDrafts: [],
  reasoningSegments: [],
  assistantOutputSegments: [],
  todos: [],
  inlineRequests: [],
  presentations: [],
};

function summarizeValue(v: unknown, max = 160): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v.length > max ? v.slice(0, max) + "…" : v;
  try {
    const s = JSON.stringify(v);
    return s.length > max ? s.slice(0, max) + "…" : s;
  } catch {
    return String(v);
  }
}

function hasPayloadValue(p: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(p, key) && p[key] !== undefined;
}

function summarizePayloadValue(p: Record<string, unknown>, key: string): string | undefined {
  return hasPayloadValue(p, key) ? summarizeValue(p[key]) : undefined;
}

function messageFromPayloadValue(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "object" && "message" in value) {
    const message = (value as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  const summary = summarizeValue(value);
  return summary || undefined;
}

function stringPayload(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function numberPayload(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function sequenceOf(event: AgentStreamEvent): number {
  return typeof event.sequence === "number" ? event.sequence : Number.MAX_SAFE_INTEGER;
}

function applyToolInputDelta(
  drafts: ToolInputDraft[],
  event: AgentStreamEvent,
): ToolInputDraft[] {
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  const index = numberPayload(payload.index);
  const inputStreamId = stringPayload(payload.input_stream_id);
  const delta = stringPayload(payload.input_delta);
  if (payload.index !== undefined && index === undefined) return drafts;
  if (!inputStreamId || !delta) return drafts;

  const existing = drafts.find((draft) => draft.inputStreamId === inputStreamId);
  const patch: ToolInputDraft = {
    inputStreamId,
    toolCallId: stringPayload(payload.tool_call_id) ?? existing?.toolCallId,
    toolName: stringPayload(payload.name) ?? existing?.toolName,
    inputText: `${existing?.inputText ?? ""}${delta}`,
    status: existing?.status ?? "streaming",
    sequence: existing?.sequence ?? sequenceOf(event),
    lastSequence: sequenceOf(event),
    createdAt: existing?.createdAt ?? event.timestamp,
    updatedAt: event.timestamp,
  };

  return existing
    ? drafts.map((draft) => (draft.inputStreamId === inputStreamId ? patch : draft))
    : [...drafts, patch];
}

function bindToolInputDraft(
  drafts: ToolInputDraft[],
  event: AgentStreamEvent,
  status: ToolInputDraft["status"],
): ToolInputDraft[] {
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  const inputStreamId = stringPayload(payload.input_stream_id);
  const toolCallId = stringPayload(payload.tool_call_id);
  if (!inputStreamId && !toolCallId) return drafts;

  return drafts.map((draft) => {
    const matches =
      (inputStreamId && draft.inputStreamId === inputStreamId) ||
      (toolCallId && draft.toolCallId === toolCallId);
    if (!matches) return draft;
    return {
      ...draft,
      toolCallId: toolCallId ?? draft.toolCallId,
      toolName: stringPayload(payload.name) ?? stringPayload(payload.tool_name) ?? draft.toolName,
      status,
      lastSequence: sequenceOf(event),
      updatedAt: event.timestamp,
    };
  });
}

function withEventSequence(state: RunStreamState, event: AgentStreamEvent): RunStreamState {
  const sequence = sequenceOf(event);
  if (!Number.isFinite(sequence) || sequence === Number.MAX_SAFE_INTEGER) return state;
  return {
    ...state,
    lastEventSequence: Math.max(state.lastEventSequence ?? 0, sequence),
  };
}

function reasoningSegmentId(event: AgentStreamEvent, p: Record<string, unknown>): string {
  const explicit =
    (p.reasoning_id as string | undefined) ??
    (p.thinking_id as string | undefined) ??
    (p.segment_id as string | undefined);
  if (explicit) return explicit;

  if (event.type === "model.reasoning_delta") return `${event.run_id}:model-reasoning`;

  const messageId = p.message_id as string | undefined;
  return messageId ? `${messageId}:reasoning` : event.id;
}

const REASONING_CHUNK_SEPARATOR = ":chunk:";

function reasoningSegmentBaseId(id: string): string {
  const separatorIndex = id.indexOf(REASONING_CHUNK_SEPARATOR);
  return separatorIndex >= 0 ? id.slice(0, separatorIndex) : id;
}

function segmentSequence(segment: ReasoningSegment): number | undefined {
  return segment.lastSequence ?? segment.sequence;
}

function latestReasoningSegmentForBase(
  segments: ReasoningSegment[],
  baseId: string,
): ReasoningSegment | undefined {
  return segments
    .filter((segment) => reasoningSegmentBaseId(segment.id) === baseId)
    .sort((a, b) => (segmentSequence(b) ?? -1) - (segmentSequence(a) ?? -1))[0];
}

function hasToolEventBetween(state: RunStreamState, after: number | undefined, before: number): boolean {
  if (after == null || before <= after) return false;
  return state.toolCalls.some((tool) => {
    const sequences = [tool.sequence, tool.lastSequence].filter(
      (value): value is number => typeof value === "number",
    );
    return sequences.some((sequence) => sequence > after && sequence < before);
  });
}

function hasAssistantOutputBetween(state: RunStreamState, after: number | undefined, before: number): boolean {
  if (after == null || before <= after) return false;
  return (state.assistantOutputSegments ?? []).some((segment) => {
    const sequences = [segment.sequence, segment.lastSequence, segment.completedSequence].filter(
      (value): value is number => typeof value === "number",
    );
    return sequences.some((sequence) => sequence > after && sequence < before);
  });
}

function hasProcessEventBetween(state: RunStreamState, after: number | undefined, before: number): boolean {
  if (after == null || before <= after) return false;
  const processSequences = [
    ...state.toolCalls.flatMap((tool) => [tool.sequence, tool.lastSequence]),
    ...state.reasoningSegments.flatMap((segment) => [segment.sequence, segment.lastSequence]),
    ...state.todos.map((todo) => todo.sequence),
    ...(state.presentations ?? []).flatMap((p) => [p.sequence, p.lastSequence]),
  ].filter((value): value is number => typeof value === "number");

  return processSequences.some((sequence) => sequence > after && sequence < before);
}

function reasoningPayloadText(p: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = messageFromPayloadValue(p[key]);
    if (value) return value;
  }
  return "";
}

function upsertReasoningSegment(
  state: RunStreamState,
  event: AgentStreamEvent,
  options: {
    append?: boolean;
    streaming?: boolean;
    completed?: boolean;
    text?: string;
  } = {},
): RunStreamState {
  const p = (event.payload ?? {}) as Record<string, unknown>;
  const baseId = reasoningSegmentId(event, p);
  const eventSequence = sequenceOf(event);
  let currentSegments = state.reasoningSegments ?? [];
  let existing =
    options.append || options.completed
      ? latestReasoningSegmentForBase(currentSegments, baseId)
      : currentSegments.find((segment) => segment.id === baseId);
  let id = existing?.id ?? baseId;

  if (
    options.append &&
    existing &&
    (hasToolEventBetween(state, segmentSequence(existing), eventSequence) ||
      hasAssistantOutputBetween(state, segmentSequence(existing), eventSequence))
  ) {
    const previousId = existing.id;
    currentSegments = currentSegments.map((segment) =>
      segment.id === previousId
        ? {
            ...segment,
            streaming: false,
            completedAt: segment.completedAt ?? event.timestamp,
            updatedAt: event.timestamp,
          }
        : segment,
    );
    existing = undefined;
    id = `${baseId}${REASONING_CHUNK_SEPARATOR}${eventSequence}`;
  }

  const nextText = options.text ?? "";
  const content = options.append
    ? `${existing?.content ?? ""}${nextText}`
    : nextText || existing?.content || "";
  const patch: ReasoningSegment = {
    id,
    content,
    streaming: options.completed ? false : options.streaming ?? existing?.streaming ?? false,
    sequence: existing?.sequence ?? eventSequence,
    lastSequence: eventSequence,
    createdAt: existing?.createdAt ?? event.timestamp,
    updatedAt: event.timestamp,
    completedAt: options.completed ? event.timestamp : existing?.completedAt,
  };

  if (existing) {
    return {
      ...state,
      reasoningSegments: currentSegments.map((segment) =>
        segment.id === id ? { ...segment, ...patch } : segment,
      ),
    };
  }

  return {
    ...state,
    reasoningSegments: [...currentSegments, patch],
  };
}

function upsertInlineRequest(
  state: RunStreamState,
  req: InlineRequest,
  status: RunStreamState["status"],
): RunStreamState {
  const exists = state.inlineRequests.some(
    (current) => current.kind === req.kind && current.id === req.id && current.runId === req.runId,
  );
  return {
    ...state,
    status,
    inlineRequests: exists
      ? state.inlineRequests.map((current) =>
          current.kind === req.kind && current.id === req.id && current.runId === req.runId
            ? req
            : current,
        )
      : [...state.inlineRequests, req],
  };
}

function updateAssistantOutputSegment(
  state: RunStreamState,
  event: AgentStreamEvent,
  messageId: string,
  delta: string,
): RunStreamState {
  const currentSegments = state.assistantOutputSegments ?? [];
  const messageSegments = currentSegments.filter((segment) => segment.id.startsWith(`${messageId}:output:`));
  const latest = messageSegments.at(-1);
  const eventSequence = sequenceOf(event);
  const shouldStartSegment = !latest || hasProcessEventBetween(state, latest.lastSequence ?? latest.sequence, eventSequence);
  const segmentId = shouldStartSegment ? `${messageId}:output:${eventSequence}` : latest.id;

  if (!shouldStartSegment && latest) {
    return {
      ...state,
      assistantOutputSegments: currentSegments.map((segment) =>
        segment.id === latest.id
          ? {
              ...segment,
              content: segment.content + delta,
              streaming: true,
              lastSequence: eventSequence,
              updatedAt: event.timestamp,
            }
          : segment,
      ),
    };
  }

  const closedSegments = latest
    ? currentSegments.map((segment) =>
        segment.id === latest.id
          ? {
              ...segment,
              streaming: false,
              completedAt: segment.completedAt ?? event.timestamp,
              updatedAt: event.timestamp,
            }
          : segment,
      )
    : currentSegments;

  return {
    ...state,
    assistantOutputSegments: [
      ...closedSegments,
      {
        id: segmentId,
        role: "assistant",
        content: delta,
        streaming: true,
        sequence: eventSequence,
        lastSequence: eventSequence,
        createdAt: event.timestamp,
        updatedAt: event.timestamp,
      },
    ],
  };
}

function completeAssistantOutputSegments(
  state: RunStreamState,
  event: AgentStreamEvent,
  messageId: string,
  content?: string,
): RunStreamState {
  const currentSegments = state.assistantOutputSegments ?? [];
  const messageSegments = currentSegments.filter((segment) => segment.id.startsWith(`${messageId}:output:`));
  if (messageSegments.length === 0 && content) {
    return {
      ...state,
      assistantOutputSegments: [
        ...currentSegments,
        {
          id: `${messageId}:output:${sequenceOf(event)}`,
          role: "assistant",
          content,
          streaming: false,
          sequence: sequenceOf(event),
          lastSequence: sequenceOf(event),
          completedSequence: sequenceOf(event),
          createdAt: event.timestamp,
          updatedAt: event.timestamp,
          completedAt: event.timestamp,
        },
      ],
    };
  }

  const reconciledSegments = content
    ? reconcileAssistantOutputSegments(currentSegments, messageId, content)
    : currentSegments;
  const latestId = messageSegments.at(-1)?.id;
  return {
    ...state,
    assistantOutputSegments: reconciledSegments.map((segment) =>
      segment.id === latestId
        ? {
            ...segment,
            streaming: false,
            lastSequence: sequenceOf(event),
            completedSequence: sequenceOf(event),
            updatedAt: event.timestamp,
            completedAt: event.timestamp,
          }
        : segment.id.startsWith(`${messageId}:output:`)
          ? {
              ...segment,
              streaming: false,
              completedAt: segment.completedAt ?? event.timestamp,
              updatedAt: event.timestamp,
            }
          : segment,
    ),
  };
}

function reconcileAssistantOutputSegments(
  segments: ChatMessage[],
  messageId: string,
  completedContent: string,
): ChatMessage[] {
  const sourcePrefix = `${messageId}:output:`;
  const indexedSegments = segments
    .map((segment, index) => ({ segment, index }))
    .filter(({ segment }) => segment.id.startsWith(sourcePrefix));
  if (indexedSegments.length === 0) return segments;

  const currentContent = indexedSegments.map(({ segment }) => segment.content).join("");
  if (!completedContent || currentContent === completedContent) return segments;

  let cursor = 0;
  const repairedContentByIndex = new Map<number, string>();
  for (const { segment, index } of indexedSegments) {
    if (!segment.content) {
      repairedContentByIndex.set(index, "");
      continue;
    }
    const position = completedContent.indexOf(segment.content, cursor);
    if (position < 0) return segments;
    repairedContentByIndex.set(index, completedContent.slice(cursor, position) + segment.content);
    cursor = position + segment.content.length;
  }

  const last = indexedSegments[indexedSegments.length - 1];
  if (last && cursor < completedContent.length) {
    repairedContentByIndex.set(
      last.index,
      (repairedContentByIndex.get(last.index) ?? last.segment.content) +
        completedContent.slice(cursor),
    );
  }

  return segments.map((segment, index) =>
    repairedContentByIndex.has(index)
      ? { ...segment, content: repairedContentByIndex.get(index) ?? segment.content }
      : segment,
  );
}

/** Reducer that projects AgentStreamEvent into a chat-view state. */
export function reduceEvent(state: RunStreamState, event: AgentStreamEvent): RunStreamState {
  state = withEventSequence(state, event);
  const type = event.type as string;
  const p = (event.payload ?? {}) as Record<string, unknown>;

  switch (type) {
    case "run.created":
    case "run.started":
    case "run.resumed":
      return {
        ...state,
        status: (p.status as AgentRunStatus) ?? "running",
        error: undefined,
        runStartedSequence: state.runStartedSequence ?? sequenceOf(event),
        runStartedAt: state.runStartedAt ?? event.timestamp,
      };

    case "model.started":
      return {
        ...state,
        status: state.status === "idle" ? "running" : state.status,
        modelStartedSequence: state.modelStartedSequence ?? sequenceOf(event),
        modelStartedAt: state.modelStartedAt ?? event.timestamp,
      };

    case "model.completed":
      return {
        ...state,
        modelCompletedSequence: sequenceOf(event),
        modelCompletedAt: event.timestamp,
      };

    case "message.created": {
      const role = (p.role as string) === "user" ? "user" : "assistant";
      const content = (p.content as string) ?? "";
      // Avoid duplicating a message that we already have (e.g. user echo).
      const id = (p.message_id as string) ?? event.id;
      if (state.messages.some((m) => m.id === id)) return state;
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id,
            role,
            content,
            sequence: sequenceOf(event),
            lastSequence: sequenceOf(event),
            createdAt: event.timestamp,
            updatedAt: event.timestamp,
          },
        ],
      };
    }

    case "message.delta": {
      const id = (p.message_id as string) ?? "assistant-streaming";
      const delta = (p.delta as string) ?? (p.content as string) ?? "";
      const existing = state.messages.find((m) => m.id === id);
      let nextState: RunStreamState;
      if (existing) {
        nextState = {
          ...state,
          messages: state.messages.map((m) =>
            m.id === id
              ? {
                  ...m,
                  content: m.content + delta,
                  streaming: true,
                  lastSequence: sequenceOf(event),
                  updatedAt: event.timestamp,
                }
              : m,
          ),
        };
      } else {
        nextState = {
          ...state,
          messages: [
            ...state.messages,
            {
              id,
              role: "assistant",
              content: delta,
              streaming: true,
              sequence: sequenceOf(event),
              lastSequence: sequenceOf(event),
              createdAt: event.timestamp,
              updatedAt: event.timestamp,
            },
          ],
        };
      }
      return updateAssistantOutputSegment(nextState, event, id, delta);
    }

    case "reasoning.created":
    case "thinking.created":
    case "message.reasoning.created":
    case "message.thinking.created": {
      const text = reasoningPayloadText(p, ["content", "text", "reasoning", "thinking"]);
      return upsertReasoningSegment(state, event, {
        text,
        streaming: true,
      });
    }

    case "reasoning.delta":
    case "thinking.delta":
    case "model.reasoning_delta":
    case "message.reasoning.delta":
    case "message.thinking.delta": {
      const text = reasoningPayloadText(p, [
        "delta",
        "content_delta",
        "reasoning_delta",
        "thinking_delta",
        "content",
        "text",
        "reasoning",
        "thinking",
      ]);
      return upsertReasoningSegment(state, event, {
        text,
        append: true,
        streaming: true,
      });
    }

    case "reasoning.completed":
    case "thinking.completed":
    case "message.reasoning.completed":
    case "message.thinking.completed": {
      const text = reasoningPayloadText(p, ["content", "text", "reasoning", "thinking"]);
      return upsertReasoningSegment(state, event, {
        text,
        completed: true,
      });
    }

    case "message.completed":
    case "message.failed": {
      const id = (p.message_id as string) ?? "assistant-streaming";
      const content = (p.content as string) ?? undefined;
      const existing = state.messages.find((m) => m.id === id);
      const patch: Partial<ChatMessage> = {
        streaming: false,
        completedSequence: sequenceOf(event),
        lastSequence: sequenceOf(event),
        updatedAt: event.timestamp,
        completedAt: event.timestamp,
      };
      if (!existing) {
        const role: ChatMessage["role"] = (p.role as string) === "user" ? "user" : "assistant";
        const nextState: RunStreamState = {
          ...state,
          messages: [
            ...state.messages,
            {
              id,
              role,
              content: content ?? "",
              sequence: sequenceOf(event),
              ...patch,
            },
          ],
        };
        return role === "assistant"
          ? completeAssistantOutputSegments(nextState, event, id, content)
          : nextState;
      }
      const nextState: RunStreamState = {
        ...state,
        messages: state.messages.map((m) =>
          m.id === id
            ? {
                ...m,
                ...patch,
                content: content ?? m.content,
              }
            : m,
        ),
      };
      return existing.role === "assistant"
        ? completeAssistantOutputSegments(nextState, event, id, content)
        : nextState;
    }

    case "tool.input_delta": {
      return {
        ...state,
        toolInputDrafts: applyToolInputDelta(state.toolInputDrafts ?? [], event),
      };
    }

    case "tool.proposed":
    case "tool.prepare":
    case "tool.execute":
    case "tool.started":
    case "tool.completed":
    case "tool.failed":
    case "tool.denied": {
      const id = (p.tool_call_id as string) ?? event.id;
      const toolName = (p.tool_name as string) ?? (p.name as string) ?? "tool";
      const statusMap: Record<string, ToolCallEntry["status"]> = {
        "tool.proposed": "proposed",
        "tool.prepare": "proposed",
        "tool.execute": "started",
        "tool.started": "started",
        "tool.completed": "completed",
        "tool.failed": "failed",
        "tool.denied": "denied",
      };
      const existing = state.toolCalls.find((t) => t.id === id);
      const patch: Partial<ToolCallEntry> = {
        toolName,
        status: statusMap[type],
        riskLevel: (p.risk_level as string) ?? existing?.riskLevel,
        inputSummary: summarizePayloadValue(p, "input") ?? existing?.inputSummary,
        outputSummary:
          summarizePayloadValue(p, "output") ??
          summarizePayloadValue(p, "result") ??
          existing?.outputSummary,
        error:
          messageFromPayloadValue(p.error) ??
          messageFromPayloadValue(p.reason) ??
          existing?.error,
        approvalPolicy: (p.approval_policy as string) ?? existing?.approvalPolicy,
        sequence: existing?.sequence ?? sequenceOf(event),
        lastSequence: sequenceOf(event),
        createdAt: existing?.createdAt ?? event.timestamp,
        updatedAt: event.timestamp,
      };
      const nextToolInputDrafts =
        type === "tool.proposed"
          ? bindToolInputDraft(state.toolInputDrafts ?? [], event, "proposed")
          : type === "tool.completed"
            ? bindToolInputDraft(state.toolInputDrafts ?? [], event, "completed")
            : type === "tool.failed"
              ? bindToolInputDraft(state.toolInputDrafts ?? [], event, "failed")
              : type === "tool.denied"
                ? bindToolInputDraft(state.toolInputDrafts ?? [], event, "denied")
                : state.toolInputDrafts ?? [];
      if (existing) {
        return {
          ...state,
          toolInputDrafts: nextToolInputDrafts,
          toolCalls: state.toolCalls.map((t) => (t.id === id ? { ...t, ...patch } : t)),
        };
      }
      return {
        ...state,
        toolInputDrafts: nextToolInputDrafts,
        toolCalls: [...state.toolCalls, { id, ...patch } as ToolCallEntry],
      };
    }

    case "todo.created":
    case "todo.updated":
    case "todo.completed":
    case "todo.blocked":
    case "todo.cancelled": {
      const id = (p.todo_id as string) ?? (p.id as string) ?? event.id;
      const title = (p.title as string) ?? (p.text as string) ?? "";
      const statusMap: Record<string, string> = {
        "todo.created": "pending",
        "todo.updated": (p.status as string) ?? "pending",
        "todo.completed": "done",
        "todo.blocked": "blocked",
        "todo.cancelled": "cancelled",
      };
      const status = statusMap[type];
      const existing = state.todos.find((t) => t.id === id);
      if (existing) {
        return {
          ...state,
          todos: state.todos.map((t) =>
            t.id === id
              ? { ...t, title: title || t.title, status: status || t.status, sequence: t.sequence ?? sequenceOf(event) }
              : t,
          ),
        };
      }
      return { ...state, todos: [...state.todos, { id, title, status, sequence: sequenceOf(event) }] };
    }

    case "input.request":
    case "input.requested": {
      const requestId = (p.input_request_id as string) ?? (p.request_id as string) ?? event.id;
      const options = Array.isArray(p.options) ? (p.options as string[]) : undefined;
      const req: InlineRequest = {
        kind: "input",
        id: requestId,
        prompt: (p.prompt as string) ?? (p.message as string),
        runId: event.run_id,
        sequence: sequenceOf(event),
        createdAt: event.timestamp,
      };
      if (options) req.options = options;
      return upsertInlineRequest(state, req, "waiting_input");
    }

    case "input.received": {
      const reqId = (p.input_request_id as string) ?? (p.request_id as string) ?? "";
      return {
        ...state,
        inlineRequests: reqId
          ? state.inlineRequests.filter((r) => r.id !== reqId)
          : state.inlineRequests.filter((r) => !(r.kind === "input" && r.runId === event.run_id)),
        status: "running",
      };
    }

    case "approval.requested": {
      const req: InlineRequest = {
        kind: "approval",
        id: (p.approval_id as string) ?? event.id,
        prompt: (p.reason as string) ?? (p.prompt as string),
        approvalId: (p.approval_id as string),
        toolName: (p.tool_name as string),
        runId: event.run_id,
        sequence: sequenceOf(event),
        createdAt: event.timestamp,
      };
      return upsertInlineRequest(state, req, "waiting_approval");
    }

    case "approval.resolved":
    case "approval.expired": {
      const id = (p.approval_id as string) ?? "";
      return {
        ...state,
        inlineRequests: state.inlineRequests.filter((r) => r.id !== id),
      };
    }

    case "external_approval.requested": {
      const req: InlineRequest = {
        kind: "external_approval",
        id: (p.approval_id as string) ?? event.id,
        prompt: (p.reason as string),
        runId: event.run_id,
        sequence: sequenceOf(event),
        createdAt: event.timestamp,
      };
      return upsertInlineRequest(state, req, "waiting_approval");
    }

    case "model.usage": {
      return {
        ...state,
        tokenUsage: {
          input: (p.input_tokens as number) ?? state.tokenUsage?.input,
          output: (p.output_tokens as number) ?? state.tokenUsage?.output,
          total: (p.total_tokens as number) ?? state.tokenUsage?.total,
        },
      };
    }

    case "run.completed":
      return {
        ...state,
        status: "completed",
        runCompletedSequence: sequenceOf(event),
        runCompletedAt: event.timestamp,
      };

    case "run.failed":
      return {
        ...state,
        status: "failed",
        error: messageFromPayloadValue(p.error) ?? messageFromPayloadValue(p.reason) ?? "Run failed",
        runCompletedSequence: sequenceOf(event),
        runCompletedAt: event.timestamp,
      };

    case "run.cancelled":
      return {
        ...state,
        status: "cancelled",
        runCompletedSequence: sequenceOf(event),
        runCompletedAt: event.timestamp,
      };

    case "run.paused":
      return { ...state, status: (p.status as AgentRunStatus) ?? state.status };

    case "presentation.created":
    case "presentation.updated": {
      const rawPresentation = p.presentation;
      if (!rawPresentation || typeof rawPresentation !== "object") return state;
      const payload = rawPresentation as Record<string, unknown>;
      const id = (payload.id as string | undefined) ?? event.id;
      const existing = (state.presentations ?? []).find((item) => item.id === id);
      const patch: PresentationEntry = {
        id,
        status: (payload.status as PresentationEntry["status"] | undefined) ?? existing?.status ?? "ready",
        priority: (payload.priority as PresentationEntry["priority"] | undefined) ?? existing?.priority ?? "normal",
        title: (payload.title as string | undefined) ?? existing?.title ?? "Presentation",
        summary: (payload.summary as string | undefined) ?? existing?.summary,
        reason: (payload.reason as string | undefined) ?? existing?.reason,
        resource: (payload.resource as PresentationEntry["resource"] | undefined) ?? existing?.resource ?? { kind: "none" },
        surfaces: (payload.surfaces as PresentationEntry["surfaces"] | undefined) ?? existing?.surfaces ?? ["conversation"],
        preferredView: (payload.preferred_view as PresentationEntry["preferredView"] | undefined) ?? existing?.preferredView ?? "none",
        availableViews: (payload.available_views as PresentationEntry["availableViews"] | undefined) ?? existing?.availableViews ?? ["none"],
        effects: (payload.effects as PresentationEntry["effects"] | undefined) ?? existing?.effects,
        actions: (payload.actions as PresentationEntry["actions"] | undefined) ?? existing?.actions,
        metadata: (payload.metadata as Record<string, unknown> | undefined) ?? existing?.metadata,
        sequence: existing?.sequence ?? sequenceOf(event),
        lastSequence: sequenceOf(event),
        createdAt: existing?.createdAt ?? event.timestamp,
        updatedAt: event.timestamp,
      };
      return {
        ...state,
        presentations: existing
          ? state.presentations.map((item) => (item.id === id ? { ...item, ...patch } : item))
          : [...state.presentations, patch],
      };
    }

    case "subagent.delegate":
    case "subagent.started":
    case "subagent.completed":
    case "subagent.failed":
      // Subagent events are surfaced in the inspection panel; no chat mutation.
      return state;

    default:
      return state;
  }
}

export function buildRunStreamState(events: AgentStreamEvent[]): RunStreamState {
  let state: RunStreamState = { ...initialState, status: "idle" };
  for (const event of events) {
    state = reduceEvent(state, event);
  }
  const lastRun = [...events].reverse().find((event) => event.type.startsWith("run."));
  if (lastRun) {
    state = {
      ...state,
      status: ((lastRun.payload as Record<string, unknown>).status as AgentRunStatus) ?? state.status,
    };
  }
  return state;
}

const TERMINAL: AgentRunStatus[] = ["completed", "failed", "cancelled"];
const STREAM_REVEAL_INTERVAL_MS = 16;
const STREAM_REVEAL_CHARS_PER_TICK = 3;
const STREAM_RECONNECT_DELAY_MS = 250;

export interface RunStreamClient {
  stream: (
    runId: string,
    onEvent: (event: AgentStreamEvent) => void,
    signal?: AbortSignal,
    afterSequence?: number,
  ) => Promise<void>;
}

export interface FollowRunStreamOptions {
  initialState: RunStreamState;
  onState: (state: RunStreamState) => void;
  signal?: AbortSignal;
  reconnectDelayMs?: number;
}

function isTerminalStatus(status: RunStreamState["status"]): boolean {
  return status !== "idle" && TERMINAL.includes(status);
}

function waitForRunStreamReconnect(delayMs: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted || delayMs <= 0) return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      globalThis.clearTimeout(timeout);
      signal?.removeEventListener("abort", done);
      resolve();
    };
    const timeout = globalThis.setTimeout(done, delayMs);
    signal?.addEventListener("abort", done, { once: true });
  });
}

export async function followRunStreamUntilTerminal(
  runId: string,
  client: RunStreamClient,
  options: FollowRunStreamOptions,
): Promise<void> {
  let current = options.initialState;
  const applyEvent = (event: AgentStreamEvent) => {
    current = reduceEvent(current, event);
    options.onState(current);
  };

  while (!options.signal?.aborted && !isTerminalStatus(current.status)) {
    try {
      await client.stream(runId, applyEvent, options.signal, current.lastEventSequence ?? 0);
    } catch {
      if (options.signal?.aborted) return;
    }
    if (options.signal?.aborted || isTerminalStatus(current.status)) return;
    await waitForRunStreamReconnect(
      options.reconnectDelayMs ?? STREAM_RECONNECT_DELAY_MS,
      options.signal,
    );
  }
}

function revealText(currentText: string, targetText: string, maxChars: number): string {
  if (!targetText.startsWith(currentText)) return targetText;
  if (currentText.length >= targetText.length) return targetText;
  return targetText.slice(0, currentText.length + maxChars);
}

function shouldRevealText(
  current: { content: string } | undefined,
  target: { content: string; streaming?: boolean },
): boolean {
  return Boolean(target.streaming || (current && current.content !== target.content));
}

function revealMessageText(
  currentMessages: ChatMessage[],
  targetMessage: ChatMessage,
  maxChars: number,
): ChatMessage {
  const current = currentMessages.find((message) => message.id === targetMessage.id);
  if (!shouldRevealText(current, targetMessage)) return targetMessage;
  const content = revealText(current?.content ?? "", targetMessage.content, maxChars);
  return {
    ...targetMessage,
    content,
    streaming: targetMessage.streaming || content !== targetMessage.content,
  };
}

function revealReasoningText(
  currentSegments: ReasoningSegment[],
  targetSegment: ReasoningSegment,
  maxChars: number,
): ReasoningSegment {
  const current = currentSegments.find((segment) => segment.id === targetSegment.id);
  if (!shouldRevealText(current, targetSegment)) return targetSegment;
  const content = revealText(current?.content ?? "", targetSegment.content, maxChars);
  return {
    ...targetSegment,
    content,
    streaming: targetSegment.streaming || content !== targetSegment.content,
  };
}

function entrySequence(entry: {
  sequence?: number;
  lastSequence?: number;
  completedSequence?: number;
}): number {
  return entry.sequence ?? entry.completedSequence ?? entry.lastSequence ?? Number.MAX_SAFE_INTEGER;
}

function outputSegmentSourceId(id: string): string | undefined {
  const markerIndex = id.indexOf(":output:");
  return markerIndex > 0 ? id.slice(0, markerIndex) : undefined;
}

function assistantMessagesWithOutputSegments(state: RunStreamState): Set<string> {
  return new Set(
    (state.assistantOutputSegments ?? [])
      .map((message) => outputSegmentSourceId(message.id))
      .filter((id): id is string => Boolean(id)),
  );
}

function visiblePrefixCutoff(display: RunStreamState, target: RunStreamState): number | undefined {
  const hiddenAssistantMessageIds = assistantMessagesWithOutputSegments(target);
  const pendingSequences: number[] = [];

  for (const message of target.messages) {
    if (message.role === "assistant" && hiddenAssistantMessageIds.has(message.id)) continue;
    const current = display.messages.find((item) => item.id === message.id);
    if ((current?.content ?? "") !== message.content) pendingSequences.push(entrySequence(message));
  }

  for (const segment of target.reasoningSegments) {
    const current = display.reasoningSegments.find((item) => item.id === segment.id);
    if ((current?.content ?? "") !== segment.content) pendingSequences.push(entrySequence(segment));
  }

  for (const message of target.assistantOutputSegments) {
    const current = display.assistantOutputSegments.find((item) => item.id === message.id);
    if ((current?.content ?? "") !== message.content) pendingSequences.push(entrySequence(message));
  }

  return pendingSequences.length > 0 ? Math.min(...pendingSequences) : undefined;
}

function filterVisiblePrefix<T extends { sequence?: number; lastSequence?: number; completedSequence?: number }>(
  items: T[],
  cutoff: number | undefined,
): T[] {
  if (cutoff == null) return items;
  return items.filter((item) => entrySequence(item) <= cutoff);
}

function hasPendingReveal(current: RunStreamState, target: RunStreamState): boolean {
  if (isTerminalStatus(target.status)) return false;
  return visiblePrefixCutoff(current, target) != null;
}

export function revealRunStreamState(
  current: RunStreamState,
  target: RunStreamState,
  options: { maxCharsPerTick?: number } = {},
): RunStreamState {
  if (isTerminalStatus(target.status)) return target;
  const maxChars = Math.max(1, options.maxCharsPerTick ?? STREAM_REVEAL_CHARS_PER_TICK);
  const next = {
    ...target,
    messages: target.messages.map((message) =>
      revealMessageText(current.messages, message, maxChars),
    ),
    reasoningSegments: target.reasoningSegments.map((segment) =>
      revealReasoningText(current.reasoningSegments, segment, maxChars),
    ),
    assistantOutputSegments: target.assistantOutputSegments.map((message) =>
      revealMessageText(current.assistantOutputSegments, message, maxChars),
    ),
  };
  const cutoff = visiblePrefixCutoff(next, target);
  return {
    ...next,
    messages: filterVisiblePrefix(next.messages, cutoff),
    toolCalls: filterVisiblePrefix(next.toolCalls, cutoff),
    reasoningSegments: filterVisiblePrefix(next.reasoningSegments, cutoff),
    assistantOutputSegments: filterVisiblePrefix(next.assistantOutputSegments, cutoff),
    todos: filterVisiblePrefix(next.todos, cutoff),
    inlineRequests: filterVisiblePrefix(next.inlineRequests, cutoff),
    presentations: filterVisiblePrefix(next.presentations, cutoff),
  };
}

/**
 * Subscribe to a run's SSE stream and project events into chat-view state.
 * On mount, also backfills from the run snapshot/events so re-opened threads
 * show history. Closes on terminal status.
 */
export function useRunStream(runId: string | null) {
  const [rawState, setRawState] = React.useState<RunStreamState>(initialState);
  const [displayState, setDisplayState] = React.useState<RunStreamState>(initialState);
  const [backfilledRunId, setBackfilledRunId] = React.useState<string | null>(null);
  const [streaming, setStreaming] = React.useState(false);
  const rawStateRef = React.useRef<RunStreamState>(initialState);
  const qc = useQueryClient();

  React.useEffect(() => {
    rawStateRef.current = rawState;
  }, [rawState]);

  // Backfill history when a run is selected (non-streaming).
  React.useEffect(() => {
    if (!runId) {
      rawStateRef.current = initialState;
      setRawState(initialState);
      setDisplayState(initialState);
      setBackfilledRunId(null);
      setStreaming(false);
      return;
    }
    let cancelled = false;
    rawStateRef.current = initialState;
    setRawState(initialState);
    setDisplayState(initialState);
    setBackfilledRunId(null);
    (async () => {
      try {
        const events = await runsApi.events(runId);
        if (cancelled) return;
        const nextState = buildRunStreamState(events);
        rawStateRef.current = nextState;
        setRawState(nextState);
        setDisplayState(nextState);
        setBackfilledRunId(runId);
      } catch {
        // ignore backfill errors; stream will retry
        if (!cancelled) setBackfilledRunId(runId);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  // Live stream (only for non-terminal runs).
  React.useEffect(() => {
    if (!runId) return;
    if (backfilledRunId !== runId) return;
    if (isTerminalStatus(rawStateRef.current.status)) return;

    const controller = new AbortController();
    setStreaming(true);

    followRunStreamUntilTerminal(runId, runsApi, {
      initialState: rawStateRef.current,
      signal: controller.signal,
      onState(nextState) {
        rawStateRef.current = nextState;
        setRawState(nextState);
      },
    })
      .catch(() => {
        // transport errors reconnect inside the stream follower unless aborted
      })
      .finally(() => {
        if (!controller.signal.aborted) setStreaming(false);
      });

    return () => controller.abort();
  }, [backfilledRunId, runId]);

  React.useEffect(() => {
    if (isTerminalStatus(rawState.status)) {
      setDisplayState(rawState);
      return;
    }

    let timer: number | undefined;
    const revealOnce = () => {
      setDisplayState((prev) => {
        const next = revealRunStreamState(prev, rawState);
        if (!hasPendingReveal(next, rawState) && timer !== undefined) {
          window.clearInterval(timer);
          timer = undefined;
        }
        return next;
      });
    };

    revealOnce();
    timer = window.setInterval(revealOnce, STREAM_REVEAL_INTERVAL_MS);
    return () => {
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [rawState]);

  // Invalidate run/thread queries when a run terminates so lists refresh.
  React.useEffect(() => {
    if (isTerminalStatus(rawState.status)) {
      void qc.invalidateQueries({ queryKey: ["threads"] });
      void qc.invalidateQueries({ queryKey: ["runs"] });
    }
  }, [rawState.status, qc]);

  return { state: displayState, streaming };
}
