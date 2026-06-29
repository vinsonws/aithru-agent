import { nanoid } from "nanoid";
import type { AgentToolCallResult } from "../capabilities/descriptors.js";
import type { CapabilityRouter } from "../capabilities/router.js";
import type { AgentRun } from "../contracts/types.js";
import type { AgentModelAdapter } from "../model/types.js";
import type { AgentStore } from "../persistence/protocols.js";
import { EVENT_TYPES, VISIBILITY } from "../stream/events.js";
import { AgentEventWriter } from "../stream/writer.js";
import { RunLoop } from "./run-loop.js";

export class ModelTurnLoop {
  constructor(
    private deps: {
      store: AgentStore;
      eventWriter: AgentEventWriter;
      capabilityRouter: CapabilityRouter;
      modelAdapter: AgentModelAdapter;
      maxTurns?: number;
    },
  ) {}

  async execute(run: AgentRun): Promise<AgentRun> {
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
    let toolResults: AgentToolCallResult[] = [];
    const maxTurns = this.deps.maxTurns ?? 8;

    for (let turn = 0; turn < maxTurns; turn += 1) {
      const currentRun = this.deps.store.getRun(run.id) ?? run;
      const messages = currentRun.thread_id
        ? this.deps.store.listMessages(currentRun.thread_id)
        : [];
      const events = this.deps.modelAdapter.createTurn({
        run: currentRun,
        messages,
        context: {},
        toolResults,
      });

      const nextToolResults: AgentToolCallResult[] = [];
      let sawToolCall = false;

      for await (const event of events) {
        if (event.type === "text_delta") {
          content += event.delta;
          loop.emitMessageDelta(messageId, event.delta, content);
        } else if (event.type === "reasoning_delta") {
          this.deps.eventWriter.write(
            run.id,
            currentRun.thread_id ?? null,
            EVENT_TYPES.MODEL_REASONING_DELTA,
            { delta: event.delta },
            { visibility: VISIBILITY.DEBUG, source: { kind: "model" } },
          );
        } else if (event.type === "usage") {
          this.deps.eventWriter.write(
            run.id,
            currentRun.thread_id ?? null,
            EVENT_TYPES.MODEL_USAGE,
            event,
            { visibility: VISIBILITY.AUDIT, source: { kind: "model" } },
          );
        } else if (event.type === "tool_call") {
          sawToolCall = true;
          const call = await loop.executeToolCall({
            id: event.id,
            name: event.name,
            input: event.input,
          });
          if (call.result) nextToolResults.push(call.result);
          if (call.approvalRequired) {
            loop.emitMessageCompleted(messageId, content);
            return this.deps.store.getRun(run.id)!;
          }
        } else if (event.type === "failed") {
          loop.emitMessageCompleted(messageId, content);
          loop.emitRunFailed(event.error);
          return this.deps.store.getRun(run.id)!;
        }
      }

      if (!sawToolCall) {
        loop.emitMessageCompleted(messageId, content);
        loop.emitRunCompleted({ content });
        return this.deps.store.getRun(run.id)!;
      }

      toolResults = nextToolResults;
    }

    loop.emitMessageCompleted(messageId, content);
    loop.emitRunFailed({
      code: "MODEL_TURN_LIMIT_EXCEEDED",
      message: "Model turn loop exceeded the configured turn limit",
    });
    return this.deps.store.getRun(run.id)!;
  }
}
