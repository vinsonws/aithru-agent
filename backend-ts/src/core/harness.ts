import type { AgentRun } from "../contracts/types.js";
import { InMemoryStore } from "../persistence/store.js";
import { AgentEventWriter } from "../stream/writer.js";
import type { CapabilityRouter } from "../capabilities/router.js";
import { RunLoop, type ToolCallStep } from "./run-loop.js";
import { AgentError } from "./errors.js";

export interface HarnessCore {
  execute(run: AgentRun, script: ScriptedHarnessScript): Promise<AgentRun>;
}

export interface ScriptedHarnessScript {
  steps: ToolCallStep[];
  finalContent?: string;
}

export class ScriptedHarnessCore implements HarnessCore {
  private store: InMemoryStore;
  private eventWriter: AgentEventWriter;
  private capabilityRouter: CapabilityRouter;

  constructor(deps: {
    store: InMemoryStore;
    eventWriter: AgentEventWriter;
    capabilityRouter: CapabilityRouter;
  }) {
    this.store = deps.store;
    this.eventWriter = deps.eventWriter;
    this.capabilityRouter = deps.capabilityRouter;
  }

  async execute(
    run: AgentRun,
    script: ScriptedHarnessScript,
  ): Promise<AgentRun> {
    const loop = new RunLoop({
      run,
      store: this.store,
      eventWriter: this.eventWriter,
      capabilityRouter: this.capabilityRouter,
    });

    try {
      // 1. Start
      loop.emitRunStarted();

      // 2. Emit a message for the task
      const messageId = `msg_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
      loop.emitMessageCreated(messageId, script.finalContent || "");

      // 3. Execute script steps with simulated deltas
      let accumulatedContent = "";
      for (const step of script.steps) {
        // Simulate a thinking delta before tool call
        const thinkingDelta = `\n> Calling ${step.name}...\n`;
        accumulatedContent += thinkingDelta;
        loop.emitMessageDelta(messageId, thinkingDelta, accumulatedContent);

        // Execute the tool
        await loop.executeToolCall(step);
      }

      // 4. Final content
      if (script.finalContent) {
        const finalDelta = `\n\n${script.finalContent}`;
        accumulatedContent += finalDelta;
        loop.emitMessageDelta(messageId, finalDelta, accumulatedContent);
      }

      // 5. Complete message
      loop.emitMessageCompleted(messageId, accumulatedContent);

      // 6. Complete run
      loop.emitRunCompleted({
        content: accumulatedContent,
      });

      return this.store.getRun(run.id)!;
    } catch (err: any) {
      const errorPayload = {
        code: err.code || "HARNESS_ERROR",
        message: err.message || "Harness execution failed",
      };
      loop.emitRunFailed(errorPayload);
      throw new AgentError(
        errorPayload.code,
        errorPayload.message,
        false,
        err,
      );
    }
  }
}
