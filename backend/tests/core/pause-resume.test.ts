import { describe, it, expect } from "vitest";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter } from "@aithru-agent/stream";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import { WorkerRunner } from "../../src/worker/runner.js";
import type { AgentRun } from "@aithru-agent/contracts";
import type { ToolCallStep } from "../../src/core/run-loop.js";

function createRun(scopes: string[]): AgentRun {
  return {
    id: "run_pause", org_id: "org_1", actor_user_id: "u1",
    source: "api", thread_id: null, workspace_id: "ws_pause",
    task_msg: "test", scopes, harness_options: null,
    status: "queued", started_at: new Date().toISOString().replace(/\.\d{3}/, ""),
    completed_at: null, claim: null, result: null, error: null,
  };
}

describe("Pause/Resume Flow", () => {
  it("pauses run when write tool requires approval", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new ProductionCapabilityRouter(store, eventWriter);
    const worker = new WorkerRunner({ store, eventWriter, capabilityRouter: router });

    const run = createRun(["workspace:read", "workspace:write"]);
    store.createRun(run);

    const steps: ToolCallStep[] = [
      { name: "workspace.write_file", input: { path: "/test.txt", content: "hello" } },
    ];

    const result = await worker.startRun(run, { steps });
    expect(result.status).toBe("waiting_approval");
    expect(result.current_approval_id).toBeTruthy();

    const events = store.listEvents(run.id);
    expect(events.some((e) => e.type === "approval.requested")).toBe(true);
    expect(events.some((e) => e.type === "run.paused")).toBe(true);
  });

  it("denies tool without required scopes", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new ProductionCapabilityRouter(store, eventWriter);

    const run = createRun(["workspace:read"]); // No write scope
    store.createRun(run);

    const prepareResult = await router.prepareToolCall(
      { id: "tc1", name: "workspace.write_file", input: { path: "/x", content: "y" }, run_id: run.id },
      { run },
    );
    expect(prepareResult.allowed).toBe(false);
    expect(prepareResult.reason).toContain("Missing scopes");
  });
});
