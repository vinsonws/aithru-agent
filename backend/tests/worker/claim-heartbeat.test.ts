import { describe, it, expect, beforeEach } from "vitest";
import { InMemoryStore } from "../../src/persistence/store.js";
import type { AgentRun } from "../../src/contracts/types.js";

function createRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run_claim_1",
    org_id: "org_1",
    actor_user_id: "u1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_claim_1",
    task_msg: "Claim test",
    scopes: ["*"],
    harness_options: null,
    status: "queued",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
    ...overrides,
  };
}

describe("Claim and Heartbeat (InMemoryStore)", () => {
  let store: InMemoryStore;

  beforeEach(() => {
    store = new InMemoryStore();
  });

  it("acquires a claim on an unclaimed run", () => {
    const run = createRun();
    store.createRun(run);

    const claimed = store.acquireClaim(run.id, "worker1");
    expect(claimed).toBe(true);

    const updated = store.getRun(run.id);
    expect(updated!.claim).toBeDefined();
    expect(updated!.claim!.worker_id).toBe("worker1");
    expect(updated!.claim!.attempt).toBe(1);
  });

  it("denies claim acquisition when already claimed by another worker", () => {
    const run = createRun();
    store.createRun(run);

    store.acquireClaim(run.id, "worker1");
    const result = store.acquireClaim(run.id, "worker2");
    expect(result).toBe(false);
  });

  it("releases a claim", () => {
    const run = createRun();
    store.createRun(run);

    store.acquireClaim(run.id, "worker1");
    const released = store.releaseClaim(run.id, "worker1");
    expect(released).toBe(true);

    const updated = store.getRun(run.id);
    expect(updated!.claim).toBeUndefined();
  });

  it("does not release claim for wrong worker", () => {
    const run = createRun();
    store.createRun(run);

    store.acquireClaim(run.id, "worker1");
    const released = store.releaseClaim(run.id, "worker2");
    expect(released).toBe(false);
  });

  it("finds stale claims with expired leases", async () => {
    const run = createRun();
    store.createRun(run);

    // Acquire with very short lease
    store.acquireClaim(run.id, "worker1", 1); // 1 second lease

    // Wait for lease to expire
    await new Promise((r) => setTimeout(r, 1100));

    const stale = store.findStaleClaims();
    expect(stale.length).toBeGreaterThanOrEqual(1);
    expect(stale[0].id).toBe(run.id);
  });

  it("rejects claim acquisition for nonexistent run", () => {
    expect(() => store.acquireClaim("nonexistent", "w1")).toThrow();
  });
});
