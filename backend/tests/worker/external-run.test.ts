import { describe, expect, it } from "vitest";
import type { AgentRun } from "@aithru-agent/contracts";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter } from "@aithru-agent/stream";
import { ExternalRunCoordinator } from "../../src/worker/external-run.js";

function createRun(): AgentRun {
  return {
    id: "run_external",
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    skill_id: null,
    workspace_id: "ws_external",
    task_msg: "External",
    scopes: ["*"],
    harness_options: null,
    status: "running",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
  };
}

describe("ExternalRunCoordinator", () => {
  it("pauses and resumes around provider-owned external runs", () => {
    const store = new InMemoryStore();
    const writer = new AgentEventWriter(store);
    const coordinator = new ExternalRunCoordinator(store, writer);
    const run = createRun();
    store.createRun(run);

    const waiting = coordinator.waitForExternalRun(
      run,
      "external_1",
      "workflow.report",
    );
    expect(waiting.status).toBe("waiting_external_run");

    const resumed = coordinator.resolveExternalRun(run.id, {
      external_run_id: "external_1",
      status: "completed",
      output: { ok: true },
    });
    expect(resumed.status).toBe("running");
    expect(store.listEvents(run.id).map((event) => event.type)).toEqual([
      "external_run.started",
      "external_run.resolved",
    ]);
  });
});
