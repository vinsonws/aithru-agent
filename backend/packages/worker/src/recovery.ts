import type { AgentStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import type { AgentRun } from "@aithru-agent/contracts";
import {
  createDefaultRetryPolicy,
  canRetry,
  nextRetryAt,
} from "@aithru-agent/harness";
import type { AgentRunRetryPolicy, AgentRunRetryState } from "@aithru-agent/harness";

export class RecoveryScanner {
  constructor(
    private store: AgentStore,
    private eventWriter: AgentEventWriter,
    private retryPolicy: AgentRunRetryPolicy = createDefaultRetryPolicy(),
  ) {}

  setRetryPolicy(policy: AgentRunRetryPolicy): void {
    this.retryPolicy = policy;
  }

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
      const retryState: AgentRunRetryState = {
        attempt: ((run as any).retry_state?.attempt ?? 0) + 1,
        next_retry_at: null,
        last_error: { code: "WORKER_DIED", message: "Worker lost heartbeat; run terminated" },
      };

      if (canRetry(this.retryPolicy, retryState)) {
        retryState.next_retry_at = nextRetryAt(this.retryPolicy, retryState);
      }

      this.store.updateRun(run.id, {
        status: "failed",
        completed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
        error: { code: "WORKER_DIED", message: "Worker lost heartbeat; run terminated" },
      });

      this.eventWriter.write(run.id, run.thread_id || null, EVENT_TYPES.RUN_FAILED, {
        error: { code: "WORKER_DIED", message: "Worker lost heartbeat" },
        retry_state: retryState,
      });
    }

    store.releaseClaim(run.id, workerId);
    return this.store.getRun(run.id)!;
  }
}
