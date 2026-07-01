import { nanoid } from "nanoid";
import type { AgentToolDescriptor } from "@aithru-agent/capabilities";
import type { CapabilityRouter } from "@aithru-agent/capabilities";
import { activeSkillKeysFromEvents } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import type { AgentModelAdapter, AgentModelToolResult, ModelTurnEvent } from "@aithru-agent/model";
import type { AgentStore } from "@aithru-agent/persistence";
import type { SkillResolver } from "@aithru-agent/skills";
import { EVENT_TYPES, VISIBILITY, AgentEventWriter } from "@aithru-agent/stream";
import { buildModelContextPacket, isPlanModeRun } from "./context-packet.js";
import {
  resolveRunLimits,
  countModelRequests,
  shouldWarnAtLimit,
  writeLimitWarning,
  pauseForLimitContinuation,
} from "./run-limits.js";
import { RunLoop } from "./run-loop.js";
import { runTerminalProcessors } from "./terminal-processors.js";

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
    options: { toolResults?: AgentModelToolResult[] } = {},
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
      const events = this.deps.modelAdapter.createTurn({
        run: currentRun,
        messages: contextPacket.messages,
        context: contextPacket.stats,
        tools: modelTools(tools),
        toolResults,
        turnIndex: modelRequestCount,
      });

      const nextToolResults: AgentModelToolResult[] = [];
      let sawToolCall = false;
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
        if (event.type === "text_delta") {
          flushToolInputDelta();
          content += event.delta;
          loop.emitMessageDelta(messageId, event.delta, content);
        } else if (event.type === "reasoning_delta") {
          flushToolInputDelta();
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
          const call = await loop.executeToolCall({
            id: event.id,
            name: event.name,
            input: event.input,
            inputStreamId: event.inputStreamId,
          });
          if (call.result) nextToolResults.push({ ...call.result, input: event.input });
          if (call.approvalRequired) {
            loop.emitMessageCompleted(messageId, content);
            return this.deps.store.getRun(run.id)!;
          }
          if (call.inputRequired) {
            loop.emitMessageCompleted(messageId, content);
            return this.deps.store.getRun(run.id)!;
          }
        } else if (event.type === "failed") {
          flushToolInputDelta();
          loop.emitMessageCompleted(messageId, content);
          loop.emitRunFailed(event.error);
          return this.deps.store.getRun(run.id)!;
        }
      }
      flushToolInputDelta();

      if (!sawToolCall) {
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
          phase: "after_completion",
        });
        return this.deps.store.getRun(run.id)!;
      }

      toolResults = nextToolResults;
    }

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
