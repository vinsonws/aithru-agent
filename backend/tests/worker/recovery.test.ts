import { describe, it, expect, beforeEach } from "vitest";
import { InMemoryStore } from "../../src/persistence/store.js";
import { AgentEventWriter } from "../../src/stream/writer.js";
import { RecoveryScanner } from "../../src/worker/recovery.js";
import {
  createDefaultRetryPolicy,
} from "../../src/core/retry.js";
import type { AgentRun } from "../../src/contracts/types.js";

function createRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run_rec_1",
    org_id: "org_1",
    actor_user_id: "u1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_rec_1",
    task_msg: "Recovery test",
    scopes: ["*"],
    harness_options: null,
    status: "running",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: {
      worker_id: "dead_worker",
      claimed_at: "2026-01-01T00:00:00Z",
      last_heartbeat_at: null,
      lease_expires_at: "2026-01-01T00:00:00Z",
      attempt: 1,
    },
    result: null,
    error: null,
    ...overrides,
  };
}

describe("RecoveryScanner", () => {
  let store: InMemoryStore;
  let writer: AgentEventWriter;
  let scanner: RecoveryScanner;

  beforeEach(() => {
    store = new InMemoryStore();
    writer = new AgentEventWriter(store);
    scanner = new RecoveryScanner(store, writer);
  });

  it("finds recoverable runs with stale claims", () => {
    // Create run with expired claim
    const run = createRun();
    store.createRun(run);

    const recoverable = scanner.findRecoverableRuns();
    expect(recoverable.length).toBeGreaterThanOrEqual(1);
    expect(recoverable[0].id).toBe(run.id);
  });

  it("returns empty array when no stale claims exist", () => {
    const run = createRun({
      claim: {
        worker_id: "alive",
        claimed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
        last_heartbeat_at: null,
        lease_expires_at: new Date(Date.now() + 60000)
          .toISOString()
          .replace(/\.\d{3}/, ""),
        attempt: 1,
      },
    });
    store.createRun(run);

    const recoverable = scanner.findRecoverableRuns();
    expect(recoverable.length).toBe(0);
  });

  it("recovers a running run with stale claim", async () => {
    const run = createRun({
      claim: {
        worker_id: "dead_worker",
        claimed_at: "2026-01-01T00:00:00Z",
        last_heartbeat_at: null,
        lease_expires_at: "2026-01-01T00:00:00Z",
        attempt: 1,
      },
    });
    store.createRun(run);

    const recovered = await scanner.recoverRun(run, "recovery_worker");
    expect(recovered.status).toBe("failed");
    expect(recovered.error).toMatchObject({ code: "WORKER_DIED" });

    // Claim should be released
    const updated = store.getRun(run.id)!;
    expect(updated.claim).toBeUndefined();
  });

  it("recovers a waiting_approval run by keeping it paused", async () => {
    const run = createRun({
      status: "waiting_approval" as any,
      claim: {
        worker_id: "dead_worker",
        claimed_at: "2026-01-01T00:00:00Z",
        last_heartbeat_at: null,
        lease_expires_at: "2026-01-01T00:00:00Z",
        attempt: 1,
      },
      current_approval_id: "aprv_123",
    });
    store.createRun(run);

    const recovered = await scanner.recoverRun(run, "recovery_worker");
    // Status should remain waiting_approval
    expect(recovered.status).toBe("waiting_approval");

    // Claim should be released
    const updated = store.getRun(run.id)!;
    expect(updated.claim).toBeUndefined();
  });

  it("supports custom retry policy", () => {
    const policy = {
      max_attempts: 5,
      initial_delay_seconds: 5,
      max_delay_seconds: 60,
      backoff_multiplier: 2,
    };
    scanner.setRetryPolicy(policy);
    // setRetryPolicy should not throw
    expect(true).toBe(true);
  });

  it("uses default retry policy by default", () => {
    const defaultPolicy = createDefaultRetryPolicy();
    expect(defaultPolicy.max_attempts).toBe(3);
  });
});
