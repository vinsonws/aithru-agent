import { InMemoryStore } from "../persistence/store.js";
import { AgentEventWriter } from "../stream/writer.js";
import type { CapabilityRouter } from "../capabilities/router.js";
import { ScriptedHarnessCore, type ScriptedHarnessScript } from "../core/harness.js";
import type { AgentRun } from "../contracts/types.js";
import { validateRunStatusTransition } from "../contracts/schemas.js";
import { EVENT_TYPES } from "../stream/events.js";

export class WorkerRunner {
  private harness: ScriptedHarnessCore;
  private store: InMemoryStore;
  private eventWriter: AgentEventWriter;

  constructor(deps: {
    store: InMemoryStore;
    eventWriter: AgentEventWriter;
    capabilityRouter: CapabilityRouter;
  }) {
    this.store = deps.store;
    this.eventWriter = deps.eventWriter;
    this.harness = new ScriptedHarnessCore(deps);
  }

  async startRun(
    run: AgentRun,
    script: ScriptedHarnessScript,
  ): Promise<AgentRun> {
    // Set status to running
    this.store.updateRun(run.id, { status: "running" });

    // Execute
    const completedRun = await this.harness.execute(run, script);
    return completedRun;
  }

  async resumeRun(
    runId: string,
    script: ScriptedHarnessScript,
  ): Promise<AgentRun> {
    const run = this.store.getRun(runId);
    if (!run) throw new Error(`Run ${runId} not found`);

    validateRunStatusTransition(run.status as string, "running");
    this.store.updateRun(runId, {
      status: "running",
      current_approval_id: null,
    });

    this.eventWriter.write(
      runId,
      run.thread_id ?? null,
      EVENT_TYPES.RUN_RESUMED,
      { reason: "approval_resolved" },
    );

    return this.harness.execute(run, script);
  }
}
