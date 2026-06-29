// backend-ts/examples/approval_demo.ts

import { createRuntime } from "../src/application/runtime.js";
import type { AgentRun } from "../src/contracts/types.js";
import type { ToolCallStep } from "../src/core/run-loop.js";

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

async function main() {
  const runtime = createRuntime();

  // Create a run with WRITE scopes (allowed)
  const run: AgentRun = {
    id: `run_approval_${Date.now().toString(36)}`,
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    skill_id: null,
    workspace_id: `ws_approval_${Date.now().toString(36)}`,
    task_msg: "Write a file that requires approval.",
    scopes: ["workspace:read", "workspace:write"],
    harness_options: null,
    status: "queued",
    started_at: now(),
    completed_at: null,
    claim: null,
    result: null,
    error: null,
  };
  runtime.store.createRun(run);

  // Step 1: Start run — will pause on workspace.write_file (requires approval)
  const script: ToolCallStep[] = [
    { name: "workspace.write_file", input: { path: "/secret.txt", content: "secret" } },
  ];

  console.log("Starting run...");
  const pausedRun = await runtime.worker.startRun(run, { steps: script });
  console.log(`Run status: ${pausedRun.status}`);
  console.log(`Approval ID: ${pausedRun.current_approval_id}`);

  if (pausedRun.status === "waiting_approval" && pausedRun.current_approval_id) {
    // Step 2: Resolve approval
    console.log("\nResolving approval...");
    const resolved = runtime.store.resolveApproval(
      pausedRun.current_approval_id,
      "approved",
    );
    console.log(`Approval resolved: ${resolved.status}`);

    // Step 3: Resume run
    console.log("\nResuming run...");
    const completedRun = await runtime.worker.resumeRun(pausedRun.id, {
      steps: script.slice(1), // continue from where we left off
    });
    console.log(`Run status: ${completedRun.status}`);
    console.log(`Result: ${completedRun.result?.content || "none"}`);
  }

  // Verify events
  const events = runtime.store.listEvents(run.id);
  const eventTypes = [...new Set(events.map((e) => e.type))].sort();
  console.log(`\nEvents: ${events.length}`);
  console.log(`Event types: ${eventTypes.join(", ")}`);

  // Check trace
  const { projectTraceSpans } = await import("../src/trace/projector.js");
  const spans = projectTraceSpans(events);
  console.log(`Trace spans: ${spans.length} root(s)`);
}

main().catch(console.error);
