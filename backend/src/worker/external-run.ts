import type { AgentRun } from "../contracts/types.js";
import type { AgentStore } from "../persistence/protocols.js";
import { EVENT_TYPES } from "../stream/events.js";
import { AgentEventWriter } from "../stream/writer.js";

export class ExternalRunCoordinator {
  constructor(
    private store: AgentStore,
    private eventWriter: AgentEventWriter,
  ) {}

  waitForExternalRun(
    run: AgentRun,
    externalRunId: string,
    capabilityKey: string,
  ): AgentRun {
    const updated = this.store.updateRun(run.id, {
      status: "waiting_external_run",
    });
    this.eventWriter.write(
      run.id,
      run.thread_id ?? null,
      EVENT_TYPES.EXTERNAL_RUN_STARTED,
      { external_run_id: externalRunId, capability_key: capabilityKey },
    );
    return updated;
  }

  resolveExternalRun(
    runId: string,
    result: {
      external_run_id: string;
      status: "completed" | "failed";
      output?: unknown;
    },
  ): AgentRun {
    const run = this.store.getRun(runId);
    if (!run) throw new Error(`Run ${runId} not found`);
    const updated = this.store.updateRun(runId, {
      status: result.status === "completed" ? "running" : "failed",
      error:
        result.status === "failed"
          ? { code: "EXTERNAL_RUN_FAILED", message: "External run failed" }
          : null,
    });
    this.eventWriter.write(
      runId,
      run.thread_id ?? null,
      result.status === "completed"
        ? EVENT_TYPES.EXTERNAL_RUN_RESOLVED
        : EVENT_TYPES.EXTERNAL_RUN_FAILED,
      result,
    );
    return updated;
  }
}
