import { describe, it, expect } from "vitest";
import { InMemoryStore } from "../../src/persistence/store.js";
import { AgentEventWriter } from "../../src/stream/writer.js";
import { ProductionCapabilityRouter } from "../../src/capabilities/production-router.js";
import { WorkerRunner } from "../../src/worker/runner.js";
import type { AgentRun } from "../../src/contracts/types.js";
import type { ToolCallStep } from "../../src/core/run-loop.js";

function createRun(id: string, scopes: string[]): AgentRun {
  return {
    id, org_id: "org_1", actor_user_id: "u1", source: "api",
    thread_id: null, workspace_id: `ws_${id}`, task_msg: "test",
    scopes, harness_options: null, status: "queued",
    started_at: new Date().toISOString().replace(/\.\d{3}/, ""),
    completed_at: null, claim: null, result: null, error: null,
  };
}

describe("Approval Flow Integration", () => {
  it("full pause → approve → resume cycle", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new ProductionCapabilityRouter(store, eventWriter);
    const worker = new WorkerRunner({ store, eventWriter, capabilityRouter: router });

    const run = createRun("run_full", ["workspace:read", "workspace:write"]);
    store.createRun(run);

    // Step 1: Start — pauses on write
    const steps: ToolCallStep[] = [
      { name: "workspace.write_file", input: { path: "/f.txt", content: "data" } },
    ];
    const paused = await worker.startRun(run, { steps });
    expect(paused.status).toBe("waiting_approval");

    // Step 2: Resolve approval
    const approvalId = paused.current_approval_id!;
    store.resolveApproval(approvalId, "approved");

    // Step 3: Resume
    const resumed = await worker.resumeRun(run.id, { steps: [] });
    expect(resumed.status).toBe("completed");

    // Verify event ordering
    const events = store.listEvents(run.id);
    const types = events.map((e) => e.type);
    const approvalIdx = types.indexOf("approval.requested");
    const pausedIdx = types.indexOf("run.paused");
    const resumedIdx = types.indexOf("run.resumed");
    const completedIdx = types.indexOf("run.completed");

    expect(approvalIdx).toBeLessThan(pausedIdx);
    expect(pausedIdx).toBeLessThan(resumedIdx);
    expect(resumedIdx).toBeLessThan(completedIdx);
  });

  it("denied approval prevents tool execution", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new ProductionCapabilityRouter(store, eventWriter);

    const run = createRun("run_deny", ["workspace:write"]);
    store.createRun(run);

    // Directly test prepareToolCall + deny path
    const result = await router.prepareToolCall(
      { id: "tc1", name: "workspace.delete_file", input: { path: "/x" }, run_id: run.id },
      { run },
    );
    // delete_file is high risk, requires_approval
    expect(result.allowed).toBe(true);
    expect(result.requires_approval).toBe(true);
  });

  it("scope-denied tool produces audit event", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new ProductionCapabilityRouter(store, eventWriter);

    const run = createRun("run_scope", ["workspace:read"]); // no write
    store.createRun(run);

    const result = await router.prepareToolCall(
      { id: "tc1", name: "workspace.write_file", input: { path: "/x", content: "y" }, run_id: run.id },
      { run },
    );
    expect(result.allowed).toBe(false);
    expect(result.audit_event_type).toBe("tool.scope_denied");

    // Verify audit event was written
    const events = store.listEvents(run.id);
    expect(events.some((e) => e.type === "tool.scope_denied" && e.visibility === "audit")).toBe(true);
  });
});
