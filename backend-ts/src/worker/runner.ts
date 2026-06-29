import { InMemoryStore } from "../persistence/store.js";
import { AgentEventWriter } from "../stream/writer.js";
import type { CapabilityRouter } from "../capabilities/router.js";
import { ScriptedHarnessCore, type ScriptedHarnessScript } from "../core/harness.js";
import type { AgentRun } from "../contracts/types.js";

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
}
