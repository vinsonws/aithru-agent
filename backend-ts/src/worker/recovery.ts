import type { AgentStore } from "../persistence/protocols.js";
import { AgentEventWriter } from "../stream/writer.js";
import { EVENT_TYPES } from "../stream/events.js";
import type { AgentRun } from "../contracts/types.js";

export class RecoveryScanner {
  constructor(
    private store: AgentStore,
    private eventWriter: AgentEventWriter,
  ) {}

  findRecoverableRuns(): AgentRun[] {
    const store = this.store as any;
    if (!store.findStaleClaims) return [];
    return store.findStaleClaims();
  }

  async recoverRun(run: AgentRun, workerId: string): Promise<AgentRun> {
    const store = this.store as any;
    if (!store.acquireClaim) return run;

    const claimed = store.acquireClaim(run.id, workerId);
    if (!claimed) return run;

    if (run.status === "waiting_approval") {
      // Run was waiting for approval — keep it paused, emit recovery event
      this.eventWriter.write(run.id, run.thread_id || null, "run.recovery.detected", {
        reason: "stale_claim", previous_status: run.status,
      });
    } else {
      // Running run died — mark as failed for recovery
      this.store.updateRun(run.id, {
        status: "failed",
        completed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
        error: { code: "WORKER_DIED", message: "Worker lost heartbeat; run terminated" },
      });
      this.eventWriter.write(run.id, run.thread_id || null, EVENT_TYPES.RUN_FAILED, {
        error: { code: "WORKER_DIED", message: "Worker lost heartbeat" },
      });
    }

    store.releaseClaim(run.id, workerId);
    return this.store.getRun(run.id)!;
  }
}
