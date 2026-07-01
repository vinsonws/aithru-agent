import { nanoid } from "nanoid";
import type { AgentToolDescriptor } from "@aithru-agent/capabilities";
import type { CapabilityRouter } from "@aithru-agent/capabilities";
import { activeSkillKeysFromEvents } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { TERMINAL_RUN_STATUSES } from "@aithru-agent/contracts";
import type { AgentModelAdapter, AgentModelToolResult, ModelTurnEvent } from "@aithru-agent/model";
import type { AgentStore } from "@aithru-agent/persistence";
import type { SkillResolver } from "@aithru-agent/skills";
import { EVENT_TYPES, VISIBILITY, AgentEventWriter } from "@aithru-agent/stream";
import { buildModelContextPacket, isPlanModeRun } from "./context-packet.js";
import { createDefaultRetryPolicy, delaySecondsForAttempt } from "./retry.js";
import {
  resolveRunLimits,
  countModelRequests,
  countToolExecutions,
  shouldWarnAtLimit,
  writeLimitWarning,
  pauseForLimitContinuation,
  repeatToolCallState,
} from "./run-limits.js";
import { RunLoop } from "./run-loop.js";
import { runTerminalProcessors } from "./terminal-processors.js";
import { getToolCallRecord, toolResultFromRecord } from "./tool-call-records.js";

export class ModelTurnLoop {
  constructor(
    private deps: {
      store: AgentStore;
      eventWriter: AgentEventWriter;
      capabilityRouter: CapabilityRouter;
      modelAdapter: AgentModelAdapter;
      skillResolver?: SkillResolver;
    },
  ) {}

  async execute(
    run: AgentRun,
    options: { toolResults?: AgentModelToolResult[]; signal?: AbortSignal } = {},
  ): Promise<AgentRun> {
    const loop = new RunLoop({
      run,
      store: this.deps.store,
      eventWriter: this.deps.eventWriter,
      capabilityRouter: this.deps.capabilityRouter,
    });
    loop.emitRunStarted();

    const messageId = `msg_${nanoid(12)}`;
    loop.emitMessageCreated(messageId, "");
    let content = "";
    let toolResults: AgentModelToolResult[] = options.toolResults ?? [];

    for (let turn = 0; ; turn += 1) {
      const cancelled = this.observeCancellation(run.id, options.signal);
      if (cancelled) return cancelled;
      const currentRun = this.deps.store.getRun(run.id) ?? run;
      const runEvents = this.deps.store.listEvents(run.id);

      const limits = resolveRunLimits(currentRun, runEvents);
      const modelRequestCount = countModelRequests(runEvents);
      if (modelRequestCount >= limits.maxModelRequests) {
        loop.emitMessageCompleted(messageId, content);
        return pauseForLimitContinuation({
          store: this.deps.store,
          eventWriter: this.deps.eventWriter,
          run: currentRun,
          kind: "model_requests",
          current: modelRequestCount,
          limit: limits.maxModelRequests,
          message: `Model request limit reached (${modelRequestCount}/${limits.maxModelRequests})`,
        });
      }
      if (shouldWarnAtLimit("model_requests", modelRequestCount, limits.maxModelRequests, runEvents)) {
        writeLimitWarning({
          eventWriter: this.deps.eventWriter,
          run: currentRun,
          kind: "model_requests",
          current: modelRequestCount,
          limit: limits.maxModelRequests,
          message: `Approaching model request limit (${modelRequestCount}/${limits.maxModelRequests})`,
        });
      }

      const fullMessages = currentRun.thread_id
        ? this.deps.store.listMessages(currentRun.thread_id)
        : [];
      const activeKeys = activeSkillKeysFromEvents(runEvents);
      const loadedSkills = activeKeys
        .map((key) => this.deps.skillResolver?.resolve(key, currentRun.org_id, currentRun.actor_user_id))
        .filter((skill): skill is NonNullable<typeof skill> => skill != null);
      const catalog = this.deps.skillResolver?.listVisible(currentRun.org_id, currentRun.actor_user_id) ?? [];
      const contextPacket = buildModelContextPacket({
        run: currentRun,
        messages: fullMessages,
        events: runEvents,
        latestSummary: currentRun.thread_id
          ? this.deps.store.getLatestContextSummary(currentRun.thread_id)
          : undefined,
        skillInstructions: loadedSkills.map((skill) => ({
          name: skill.name,
          instructions: skill.instructions,
        })),
        skillCatalog: catalog.map((skill) => ({
          key: skill.key,
          name: skill.name,
          description: skill.description,
        })),
        activeSkillKeys: activeKeys,
      });
      this.deps.eventWriter.write(
        run.id,
        currentRun.thread_id ?? null,
        EVENT_TYPES.CONTEXT_PACKET_BUILT,
        contextPacket.stats,
        { visibility: VISIBILITY.AUDIT, source: { kind: "harness" } },
      );
      const planMode = isPlanModeRun(currentRun);
      const tools = (await this.deps.capabilityRouter.listTools({ run: currentRun }))
        .filter((tool) => planMode || !tool.name.startsWith("todo."));
      const events = this.createTurnWithRetry({
        run: currentRun,
        messages: contextPacket.messages,
        context: contextPacket.stats,
        tools: modelTools(tools),
        toolResults: mergeToolResults(toolResultsFromRunEvents(this.deps.store, run.id, runEvents), toolResults),
        turnIndex: modelRequestCount,
        signal: options.signal,
      });

      const nextToolResults: AgentModelToolResult[] = [];
      const pendingToolCalls: ToolCallEvent[] = [];
      let sawToolCall = false;
      let turnReasoningContent = "";
      let pendingToolInputDelta: PendingToolInputDelta | null = null;
      const flushToolInputDelta = () => {
        if (!pendingToolInputDelta) return;
        const pending = pendingToolInputDelta;
        pendingToolInputDelta = null;
        this.deps.eventWriter.write(
          run.id,
          currentRun.thread_id ?? null,
          EVENT_TYPES.TOOL_INPUT_DELTA,
          {
            input_stream_id: pending.inputStreamId,
            tool_call_id: pending.toolCallId ?? null,
            index: pending.index ?? null,
            name: pending.name ?? null,
            input_delta: pending.delta,
          },
          { visibility: VISIBILITY.USER, source: { kind: "model" } },
        );
      };
      const bufferToolInputDelta = (event: ToolInputDeltaEvent) => {
        if (
          pendingToolInputDelta &&
          sameToolInputDeltaTarget(pendingToolInputDelta, event) &&
          pendingToolInputDelta.delta.length + event.delta.length <= TOOL_INPUT_DELTA_FLUSH_CHARS
        ) {
          pendingToolInputDelta.delta += event.delta;
        } else {
          flushToolInputDelta();
          pendingToolInputDelta = {
            inputStreamId: event.inputStreamId,
            toolCallId: event.toolCallId,
            index: event.index,
            name: event.name,
            delta: event.delta,
          };
        }

        if (pendingToolInputDelta.delta.length >= TOOL_INPUT_DELTA_FLUSH_CHARS) {
          flushToolInputDelta();
        }
      };

      for await (const event of events) {
        const cancelled = this.observeCancellation(run.id, options.signal);
        if (cancelled) return cancelled;
        if (event.type === "text_delta") {
          flushToolInputDelta();
          content += event.delta;
          loop.emitMessageDelta(messageId, event.delta, content);
        } else if (event.type === "reasoning_delta") {
          flushToolInputDelta();
          turnReasoningContent += event.delta;
          this.deps.eventWriter.write(
            run.id,
            currentRun.thread_id ?? null,
            EVENT_TYPES.MODEL_REASONING_DELTA,
            { delta: event.delta },
            { visibility: VISIBILITY.DEBUG, source: { kind: "model" } },
          );
        } else if (event.type === "tool_input_delta") {
          bufferToolInputDelta(event);
        } else if (event.type === "usage") {
          flushToolInputDelta();
          this.deps.eventWriter.write(
            run.id,
            currentRun.thread_id ?? null,
            EVENT_TYPES.MODEL_USAGE,
            {
              requests: 1,
              input_tokens: event.inputTokens,
              output_tokens: event.outputTokens,
              total_tokens: event.totalTokens ?? event.inputTokens + event.outputTokens,
            },
            { visibility: VISIBILITY.AUDIT, source: { kind: "model" } },
          );
        } else if (event.type === "tool_call") {
          flushToolInputDelta();
          sawToolCall = true;
          pendingToolCalls.push(event);
        } else if (event.type === "failed") {
          flushToolInputDelta();
          loop.emitMessageCompleted(messageId, content);
          loop.emitRunFailed(event.error);
          return this.deps.store.getRun(run.id)!;
        }
      }
      flushToolInputDelta();

      for (const event of pendingToolCalls) {
        const cancelled = this.observeCancellation(run.id, options.signal);
        if (cancelled) return cancelled;

        const latestRun = this.deps.store.getRun(run.id) ?? currentRun;
        const latestEvents = this.deps.store.listEvents(run.id);
        const latestLimits = resolveRunLimits(latestRun, latestEvents);
        const toolExecCount = countToolExecutions(latestEvents);
        if (toolExecCount >= latestLimits.maxToolExecutions) {
          loop.emitMessageCompleted(messageId, content);
          return pauseForLimitContinuation({
            store: this.deps.store,
            eventWriter: this.deps.eventWriter,
            run: latestRun,
            kind: "tool_executions",
            current: toolExecCount,
            limit: latestLimits.maxToolExecutions,
            message: `Tool execution limit reached (${toolExecCount}/${latestLimits.maxToolExecutions})`,
          });
        }
        if (shouldWarnAtLimit("tool_executions", toolExecCount, latestLimits.maxToolExecutions, latestEvents)) {
          writeLimitWarning({
            eventWriter: this.deps.eventWriter,
            run: latestRun,
            kind: "tool_executions",
            current: toolExecCount,
            limit: latestLimits.maxToolExecutions,
            message: `Approaching tool execution limit (${toolExecCount}/${latestLimits.maxToolExecutions})`,
          });
        }

        const repeatState = repeatToolCallState(latestEvents, event.name, event.input);
        if (repeatState === "warn" || repeatState === "pause") {
          writeLimitWarning({
            eventWriter: this.deps.eventWriter,
            run: latestRun,
            kind: "repeat_tool_call",
            current: 0,
            limit: 0,
            message: `Repeated tool call: ${event.name}`,
          });
        }
        if (repeatState === "pause") {
          loop.emitMessageCompleted(messageId, content);
          return pauseForLimitContinuation({
            store: this.deps.store,
            eventWriter: this.deps.eventWriter,
            run: latestRun,
            kind: "repeat_tool_call",
            current: 0,
            limit: 0,
            message: `Repeated tool call paused: ${event.name}`,
          });
        }

        const call = await loop.executeToolCall({
          id: event.id,
          name: event.name,
          input: event.input,
          inputStreamId: event.inputStreamId,
          reasoningContent: turnReasoningContent,
        });
        if (call.result) {
          nextToolResults.push({
            ...call.result,
            input: event.input,
            reasoning_content: turnReasoningContent,
          });
        }
        if (call.approvalRequired) {
          loop.emitMessageCompleted(messageId, content);
          return this.deps.store.getRun(run.id)!;
        }
        if (call.inputRequired) {
          loop.emitMessageCompleted(messageId, content);
          return this.deps.store.getRun(run.id)!;
        }
      }

      if (!sawToolCall) {
        const cancelled = this.observeCancellation(run.id, options.signal);
        if (cancelled) return cancelled;
        let threadMessageId: string | null = null;
        if (currentRun.thread_id && content) {
          threadMessageId = `msg_${nanoid(12)}`;
          this.deps.store.createMessage({
            id: threadMessageId,
            thread_id: currentRun.thread_id,
            role: "assistant",
            content,
            run_id: run.id,
            workspace_paths: [],
            created_at: new Date().toISOString().replace(/\.\d{3}/, ""),
          });
        }
        loop.emitMessageCompleted(messageId, content, { threadMessageId });
        await runTerminalProcessors({
          store: this.deps.store,
          eventWriter: this.deps.eventWriter,
          run: { ...currentRun, status: "completed" },
          titleModelAdapter: this.deps.modelAdapter,
          phase: "before_completion",
        });
        loop.emitRunCompleted({ content, message_id: messageId, thread_message_id: threadMessageId });
        void runTerminalProcessors({
          store: this.deps.store,
          eventWriter: this.deps.eventWriter,
          run: this.deps.store.getRun(run.id)!,
          titleModelAdapter: this.deps.modelAdapter,
          phase: "after_completion",
        });
        return this.deps.store.getRun(run.id)!;
      }

      toolResults = nextToolResults;
    }

  }

  private async *createTurnWithRetry(input: Parameters<AgentModelAdapter["createTurn"]>[0]): AsyncIterable<ModelTurnEvent> {
    const policy = (input.run as any).retry_policy ?? createDefaultRetryPolicy();
    const maxAttempts = Math.max(1, Number(policy.max_attempts ?? 1));

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      let emitted = false;
      for await (const event of this.deps.modelAdapter.createTurn(input)) {
        if (input.signal?.aborted) return;
        const retry =
          event.type === "failed" &&
          event.error.retryable === true &&
          !emitted &&
          attempt < maxAttempts;
        if (retry) {
          const delaySeconds = delaySecondsForAttempt(policy, attempt);
          const nextRetryAt = new Date(Date.now() + delaySeconds * 1000)
            .toISOString()
            .replace(/\.\d{3}/, "");
          this.deps.store.updateRun(input.run.id, {
            retry_state: {
              attempt,
              next_retry_at: nextRetryAt,
              last_error: {
                code: event.error.code,
                message: event.error.message,
              },
            },
          } as Partial<AgentRun>);
          this.deps.eventWriter.write(
            input.run.id,
            input.run.thread_id ?? null,
            "model.retry",
            {
              attempt,
              next_attempt: attempt + 1,
              max_attempts: maxAttempts,
              delay_seconds: delaySeconds,
              error: event.error,
            },
            { visibility: VISIBILITY.AUDIT, source: { kind: "model" } },
          );
          await waitForRetry(delaySeconds, input.signal);
          if (input.signal?.aborted) return;
          break;
        }

        emitted = true;
        yield event;
      }
      if (!emitted) continue;
      return;
    }
  }

  private observeCancellation(runId: string, signal?: AbortSignal): AgentRun | null {
    const latest = this.deps.store.getRun(runId);
    if (!latest) return null;
    if (latest.status === "cancelled") return latest;
    if (!signal?.aborted || TERMINAL_RUN_STATUSES.has(latest.status as any)) return null;
    const cancelled = this.deps.store.updateRun(runId, {
      status: "cancelled",
      completed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
    });
    this.deps.eventWriter.write(
      runId,
      cancelled.thread_id ?? null,
      EVENT_TYPES.RUN_CANCELLED,
      { run_id: runId },
    );
    return cancelled;
  }
}

function modelTools(
  tools: Array<Pick<AgentToolDescriptor, "name" | "description" | "input_schema">>,
) {
  return tools.map((tool) => ({
    name: tool.name,
    description: tool.description,
    input_schema: tool.input_schema,
  }));
}

const TOOL_INPUT_DELTA_FLUSH_CHARS = 1024;

type ToolInputDeltaEvent = Extract<ModelTurnEvent, { type: "tool_input_delta" }>;
type ToolCallEvent = Extract<ModelTurnEvent, { type: "tool_call" }>;

interface PendingToolInputDelta {
  inputStreamId: string;
  toolCallId?: string;
  index?: number;
  name?: string;
  delta: string;
}

function sameToolInputDeltaTarget(
  pending: PendingToolInputDelta,
  event: ToolInputDeltaEvent,
): boolean {
  return pending.inputStreamId === event.inputStreamId
    && (pending.toolCallId ?? null) === (event.toolCallId ?? null)
    && (pending.index ?? null) === (event.index ?? null)
    && (pending.name ?? null) === (event.name ?? null);
}

function toolResultsFromRunEvents(
  store: AgentStore,
  runId: string,
  events: Array<{ type: string; payload: unknown }>,
): AgentModelToolResult[] {
  const results: AgentModelToolResult[] = [];
  for (const event of events) {
    if (
      event.type !== EVENT_TYPES.TOOL_COMPLETED &&
      event.type !== EVENT_TYPES.TOOL_FAILED &&
      event.type !== EVENT_TYPES.TOOL_DENIED
    ) {
      continue;
    }
    const payload = isRecord(event.payload) ? event.payload : {};
    const id = typeof payload.tool_call_id === "string" ? payload.tool_call_id : null;
    if (!id) continue;
    const record = getToolCallRecord(store, id);
    if (!record || record.run_id !== runId) continue;
    const result = toolResultFromRecord(record);
    if (result) results.push(result);
  }
  return results;
}

function mergeToolResults(...lists: AgentModelToolResult[][]): AgentModelToolResult[] {
  const byId = new Map<string, AgentModelToolResult>();
  for (const result of lists.flat()) byId.set(result.id, result);
  return [...byId.values()];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function waitForRetry(seconds: number, signal?: AbortSignal): Promise<void> {
  if (seconds <= 0 || signal?.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timeout = setTimeout(resolve, seconds * 1000);
    signal?.addEventListener("abort", () => {
      clearTimeout(timeout);
      resolve();
    }, { once: true });
  });
}
