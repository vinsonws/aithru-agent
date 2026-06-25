import type {
  ChatMessage,
  DisplayCardEntry,
  InlineRequest,
  ReasoningSegment,
  RunStreamState,
  ToolCallEntry,
} from "./useRunStream";
import type { AgentMessage } from "../../lib/api/types";

export type AssistantProcessStep =
  | {
      kind: "reasoning";
      id: string;
      sequence: number;
      content: string;
      segment: ReasoningSegment;
    }
  | {
      kind: "tool";
      id: string;
      sequence: number;
      tool: ToolCallEntry;
    };

export type ChatTimelineItem =
  | { kind: "message"; id: string; sequence: number; message: ChatMessage }
  | { kind: "assistantProcess"; id: string; sequence: number; state: RunStreamState; steps: AssistantProcessStep[] }
  | { kind: "inlineRequest"; id: string; sequence: number; request: InlineRequest }
  | { kind: "card"; id: string; sequence: number; card: DisplayCardEntry }
  | { kind: "completion"; id: string; sequence: number };

const FALLBACK_SEQUENCE = Number.MAX_SAFE_INTEGER / 2;

const KIND_ORDER: Record<ChatTimelineItem["kind"], number> = {
  message: 0,
  assistantProcess: 1,
  card: 2,
  inlineRequest: 3,
  completion: 4,
};

export function buildChatTimeline(
  state: RunStreamState,
  threadMessages: AgentMessage[] = [],
  activeRunId: string | null = null,
  historicalRunStates: Record<string, RunStreamState> = {},
): ChatTimelineItem[] {
  const items: ChatTimelineItem[] = [];
  const hiddenAssistantRunIds = assistantRunsWithOutputSegments(
    state,
    activeRunId,
    historicalRunStates,
  );

  const messages = timelineMessages(
    state.messages,
    threadMessages,
    activeRunId,
    hiddenAssistantRunIds,
    hasAssistantOutputSegments(state),
  );
  for (const { message, sequence } of messages) {
    items.push({
      kind: "message",
      id: `message:${message.id}`,
      sequence,
      message,
    });
  }

  appendRunTimelineItems(
    items,
    state,
    "assistant-process",
    activeRunId,
    assistantProcessSequence(state, messages, activeRunId),
  );

  for (const [runId, runState] of Object.entries(historicalRunStates)) {
    if (!runId || runId === activeRunId || !shouldShowRunTimelineItems(runState)) continue;
    appendRunTimelineItems(
      items,
      runState,
      `assistant-process:${runId}`,
      runId,
      historicalAssistantProcessSequence(runId, runState, messages),
    );
  }

  for (const request of state.inlineRequests) {
    items.push({
      kind: "inlineRequest",
      id: `request:${request.kind}:${request.id}`,
      sequence: request.sequence ?? FALLBACK_SEQUENCE,
      request,
    });
  }

  if (state.status === "completed" && state.runCompletedSequence != null) {
    items.push({
      kind: "completion",
      id: "run-completed",
      sequence: completionSequence(state, messages, activeRunId, items),
    });
  }

  return items.sort((a, b) => a.sequence - b.sequence || KIND_ORDER[a.kind] - KIND_ORDER[b.kind]);
}

function historicalAssistantProcessSequence(
  runId: string,
  runState: RunStreamState,
  messages: Array<{ message: ChatMessage; sequence: number }>,
): number {
  const runMessages = messages.filter((item) => item.message.runId === runId);
  const userMessages = runMessages
    .filter((item) => item.message.role === "user")
    .map((item) => item.sequence);
  if (userMessages.length > 0) return Math.max(...userMessages) + 1;

  const assistantMessages = runMessages
    .filter((item) => item.message.role === "assistant")
    .map((item) => item.sequence);
  if (assistantMessages.length > 0) return Math.min(...assistantMessages) - 1;

  return assistantProcessSequence(runState);
}

function timelineMessages(
  streamMessages: ChatMessage[],
  threadMessages: AgentMessage[],
  activeRunId: string | null,
  hiddenAssistantRunIds: Set<string> = new Set(),
  hideStreamAssistantMessages = false,
): Array<{ message: ChatMessage; sequence: number }> {
  if (threadMessages.length === 0) {
    return streamMessages
      .filter((message) => !(hideStreamAssistantMessages && message.role === "assistant"))
      .map((message) => ({
        message,
        sequence: messageDisplaySequence(message),
      }));
  }

  const streamById = new Map(streamMessages.map((message) => [message.id, message]));
  const hasStreamAssistant = streamMessages.some((message) => message.role === "assistant");
  const activeAssistantThreadIndex = threadMessages.findIndex(
    (message) => message.run_id === activeRunId && message.role === "assistant",
  );
  const activeUserThreadIndex = latestThreadMessageIndex(threadMessages, activeRunId, "user");
  const usedStreamIds = new Set<string>();
  const messages: Array<{ message: ChatMessage; sequence: number }> = [];

  chronologicalThreadMessages(threadMessages).forEach((threadMessage, index) => {
    if (
      activeRunId &&
      threadMessage.run_id === activeRunId &&
      threadMessage.role === "assistant" &&
      hasStreamAssistant
    ) {
      return;
    }
    if (
      threadMessage.role === "assistant" &&
      threadMessage.run_id &&
      hiddenAssistantRunIds.has(threadMessage.run_id)
    ) {
      return;
    }

    const streamMessage = streamById.get(threadMessage.id);
    if (streamMessage) usedStreamIds.add(streamMessage.id);
    messages.push({
      message: {
        ...(streamMessage ?? messageFromThreadMessage(threadMessage)),
        runId: threadMessage.run_id,
        createdAt: streamMessage?.createdAt ?? threadMessage.created_at,
      },
      sequence: index * 10,
    });
  });

  for (const streamMessage of streamMessages) {
    if (usedStreamIds.has(streamMessage.id)) continue;
    if (hideStreamAssistantMessages && streamMessage.role === "assistant") continue;
    messages.push({
      message: { ...streamMessage, runId: streamMessage.runId ?? activeRunId },
      sequence: streamMessageSequence(
        streamMessage,
        threadMessages.length,
        activeUserThreadIndex,
        activeAssistantThreadIndex,
      ),
    });
  }

  return messages;
}

function chronologicalThreadMessages(threadMessages: AgentMessage[]): AgentMessage[] {
  return threadMessages
    .map((message, index) => ({ message, index, time: Date.parse(message.created_at) }))
    .sort((a, b) => {
      const aTime = Number.isFinite(a.time) ? a.time : Number.POSITIVE_INFINITY;
      const bTime = Number.isFinite(b.time) ? b.time : Number.POSITIVE_INFINITY;
      return aTime - bTime || a.index - b.index;
    })
    .map((item) => item.message);
}

function messageFromThreadMessage(message: AgentMessage): ChatMessage {
  return {
    id: message.id,
    role: message.role === "user" || message.role === "system" ? message.role : "assistant",
    content: message.content,
    runId: message.run_id,
    createdAt: message.created_at,
    updatedAt: message.created_at,
    completedAt: message.created_at,
  };
}

function messageDisplaySequence(message: ChatMessage): number {
  if (message.role === "assistant") {
    return message.completedSequence ?? message.lastSequence ?? message.sequence ?? FALLBACK_SEQUENCE;
  }
  return message.sequence ?? message.completedSequence ?? message.lastSequence ?? FALLBACK_SEQUENCE;
}

function shouldShowAssistantProcess(state: RunStreamState): boolean {
  const reasoningSegments = state.reasoningSegments ?? [];
  if (state.status === "idle") return false;
  return (
    state.modelStartedSequence != null ||
    reasoningSegments.length > 0 ||
    state.toolCalls.length > 0 ||
    state.todos.length > 0 ||
    state.status === "running" ||
    state.status === "queued"
  );
}

function displayCardsForConversation(state: RunStreamState): DisplayCardEntry[] {
  return (state.displayCards ?? []).filter(
    (card) => card.surface === "conversation" || card.surface === "both",
  );
}

function shouldShowRunTimelineItems(state: RunStreamState): boolean {
  return (
    shouldShowAssistantProcess(state) ||
    hasAssistantOutputSegments(state) ||
    displayCardsForConversation(state).length > 0
  );
}

function assistantProcessSequence(
  state: RunStreamState,
  messages: Array<{ message: ChatMessage; sequence: number }> = [],
  activeRunId: string | null = null,
): number {
  if (activeRunId && messages.length > 0) {
    const activeUsers = messages
      .filter((item) => item.message.runId === activeRunId && item.message.role === "user")
      .map((item) => item.sequence);
    if (activeUsers.length > 0) {
      return Math.max(...activeUsers) + 1;
    }
  }

  const reasoningSegments = state.reasoningSegments ?? [];
  const candidates = [
    state.modelStartedSequence,
    ...reasoningSegments.map((segment) => segment.sequence ?? segment.lastSequence),
    ...state.toolCalls.map((tool) => tool.sequence ?? tool.lastSequence),
    ...state.todos.map((todo) => todo.sequence),
  ].filter((value): value is number => typeof value === "number");

  if (candidates.length > 0) {
    return Math.min(...candidates);
  }

  const latestUser = state.messages
    .filter((message) => message.role === "user")
    .map(messageDisplaySequence)
    .filter(Number.isFinite);

  if (latestUser.length > 0) {
    return Math.max(...latestUser) + 0.1;
  }

  return state.runStartedSequence ?? FALLBACK_SEQUENCE;
}

function completionSequence(
  state: RunStreamState,
  messages: Array<{ message: ChatMessage; sequence: number }>,
  activeRunId: string | null,
  existingItems: ChatTimelineItem[] = [],
): number {
  const itemSequences = existingItems
    .map((item) => item.sequence)
    .filter((sequence) => Number.isFinite(sequence));
  if (itemSequences.length > 0) return Math.max(...itemSequences) + 1;

  if (!activeRunId) return state.runCompletedSequence ?? FALLBACK_SEQUENCE;
  const activeMessages = messages
    .filter((item) => item.message.runId === activeRunId)
    .map((item) => item.sequence);
  if (activeMessages.length > 0) return Math.max(...activeMessages) + 1;
  return state.runCompletedSequence ?? FALLBACK_SEQUENCE;
}

function latestThreadMessageIndex(
  threadMessages: AgentMessage[],
  activeRunId: string | null,
  role: AgentMessage["role"],
): number {
  if (!activeRunId) return -1;
  for (let index = threadMessages.length - 1; index >= 0; index -= 1) {
    const message = threadMessages[index];
    if (message.run_id === activeRunId && message.role === role) return index;
  }
  return -1;
}

function streamMessageSequence(
  message: ChatMessage,
  threadMessageCount: number,
  activeUserThreadIndex: number,
  activeAssistantThreadIndex: number,
): number {
  if (message.role === "assistant") {
    if (activeAssistantThreadIndex >= 0) return activeAssistantThreadIndex * 10;
    if (activeUserThreadIndex >= 0) return activeUserThreadIndex * 10 + 8;
  }
  if (message.role === "user" && activeUserThreadIndex >= 0) {
    return activeUserThreadIndex * 10;
  }
  return threadMessageCount * 10 + messageDisplaySequence(message) / 1_000;
}

function assistantProcessSteps(
  state: RunStreamState,
  reasoningSegments = state.reasoningSegments ?? [],
): AssistantProcessStep[] {
  const steps: AssistantProcessStep[] = [];

  for (const segment of reasoningSegments) {
    if (!segment.content.trim() && !segment.streaming) continue;
    steps.push({
      kind: "reasoning",
      id: `reasoning:${segment.id}`,
      sequence: segment.sequence ?? segment.lastSequence ?? FALLBACK_SEQUENCE,
      content: segment.content,
      segment,
    });
  }

  for (const tool of state.toolCalls) {
    steps.push({
      kind: "tool",
      id: `tool:${tool.id}`,
      sequence: tool.sequence ?? tool.lastSequence ?? FALLBACK_SEQUENCE,
      tool,
    });
  }

  return steps.sort((a, b) => a.sequence - b.sequence || (a.kind === "reasoning" ? -1 : 1));
}

function hasAssistantOutputSegments(state: RunStreamState): boolean {
  return (state.assistantOutputSegments ?? []).some((message) => message.content.trim().length > 0);
}

function assistantRunsWithOutputSegments(
  state: RunStreamState,
  activeRunId: string | null,
  historicalRunStates: Record<string, RunStreamState>,
): Set<string> {
  const runIds = new Set<string>();
  if (activeRunId && hasAssistantOutputSegments(state)) runIds.add(activeRunId);
  for (const [runId, runState] of Object.entries(historicalRunStates)) {
    if (hasAssistantOutputSegments(runState)) runIds.add(runId);
  }
  return runIds;
}

function appendRunTimelineItems(
  items: ChatTimelineItem[],
  state: RunStreamState,
  baseId: string,
  runId: string | null,
  baseSequence: number,
): void {
  const processSteps = assistantProcessSteps(state);
  const outputSegments = (state.assistantOutputSegments ?? []).filter(
    (message) => message.content.trim().length > 0 || message.streaming,
  );
  const displayCards = displayCardsForConversation(state);

  const units = [
    ...processSteps.map((step) => ({ kind: "process" as const, sequence: step.sequence, step })),
    ...outputSegments.map((message) => ({
      kind: "output" as const,
      sequence: messageDisplaySequence(message),
      message,
    })),
    ...displayCards.map((card) => ({
      kind: "card" as const,
      sequence: card.sequence ?? card.lastSequence ?? FALLBACK_SEQUENCE,
      card,
    })),
  ].sort((a, b) => a.sequence - b.sequence || (a.kind === "process" ? -1 : 1));

  if (units.length === 0) {
    if (!shouldShowAssistantProcess(state)) return;
    items.push({
      kind: "assistantProcess",
      id: baseId,
      sequence: baseSequence,
      state,
      steps: processSteps,
    });
    return;
  }

  const firstSequence = units[0]?.sequence ?? baseSequence;
  let processGroup: AssistantProcessStep[] = [];
  let processGroupCount = 0;
  const normalize = (sequence: number) => baseSequence + Math.max(0, sequence - firstSequence) / 1_000;
  const flushProcessGroup = () => {
    if (processGroup.length === 0) return;
    const firstStep = processGroup[0];
    items.push({
      kind: "assistantProcess",
      id: processGroupCount === 0 ? baseId : `${baseId}:${processGroupCount}`,
      sequence: normalize(firstStep.sequence),
      state,
      steps: processGroup,
    });
    processGroupCount += 1;
    processGroup = [];
  };

  for (const unit of units) {
    if (unit.kind === "process") {
      processGroup.push(unit.step);
      continue;
    }
    if (unit.kind === "card") {
      flushProcessGroup();
      items.push({
        kind: "card",
        id: `card:${unit.card.id}`,
        sequence: normalize(unit.sequence),
        card: unit.card,
      });
      continue;
    }

    flushProcessGroup();
    items.push({
      kind: "message",
      id: `message:${unit.message.id}`,
      sequence: normalize(unit.sequence),
      message: { ...unit.message, runId: unit.message.runId ?? runId },
    });
  }

  flushProcessGroup();
}
