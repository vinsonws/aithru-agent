import { nanoid } from "nanoid";
import type { AgentStore } from "@aithru-agent/persistence";
import { AgentEventWriter } from "@aithru-agent/stream";
import type { CapabilityRouter } from "@aithru-agent/capabilities";
import { ScriptedHarnessCore, type ScriptedHarnessScript } from "../core/harness.js";
import type { AgentRun } from "@aithru-agent/contracts";
import { validateRunStatusTransition } from "@aithru-agent/contracts";
import { EVENT_TYPES } from "@aithru-agent/stream";

export class WorkerRunner {
  private harness: ScriptedHarnessCore;
  private store: AgentStore;
  private eventWriter: AgentEventWriter;
  private workerId: string;

  constructor(deps: {
    store: AgentStore;
    eventWriter: AgentEventWriter;
    capabilityRouter: CapabilityRouter;
  }) {
    this.store = deps.store;
    this.eventWriter = deps.eventWriter;
    this.harness = new ScriptedHarnessCore(deps);
    this.workerId = `worker_${nanoid(8)}`;
  }

  async startRun(
    run: AgentRun,
    script: ScriptedHarnessScript,
  ): Promise<AgentRun> {
    // Acquire claim before starting
    const claimed = this.store.acquireClaim(run.id, this.workerId);
    if (!claimed) throw new Error("Run is already claimed by another worker");

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

    // Re-acquire claim
    const claimed = this.store.acquireClaim(runId, this.workerId);
    if (!claimed) throw new Error("Run is already claimed by another worker");

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
