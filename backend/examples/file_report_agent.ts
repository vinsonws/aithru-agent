import { createRuntime } from "@aithru-agent/api";
import type { ToolCallStep } from "@aithru-agent/harness";
import type { AgentRun } from "@aithru-agent/contracts";
import { EVENT_TYPES } from "@aithru-agent/stream";

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

async function main() {
  const runtime = await createRuntime();

  // Create a run (mimics what API would do)
  const run: AgentRun = {
    id: `run_file_report_${Date.now().toString(36)}`,
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    workspace_id: `ws_fr_${Date.now().toString(36)}`,
    task_msg: "Analyze workspace files and create a report.",
    scopes: ["*"],
    harness_options: null,
    status: "queued",
    started_at: now(),
    completed_at: null,
    claim: null,
    result: null,
    error: null,
  };
  runtime.store.createRun(run);
  runtime.eventWriter.write(
    run.id,
    run.thread_id ?? null,
    EVENT_TYPES.RUN_CREATED,
    { run_id: run.id, status: run.status },
  );

  // Define the scripted steps (same as Python FileReportRuntime)
  const script: ToolCallStep[] = [
    {
      name: "todo.create",
      input: { title: "Read files", status: "running" },
    },
    {
      name: "workspace.write_file",
      input: { path: "/inputs/notes.md", content: "# Notes\nImportant input.\n" },
    },
    {
      name: "workspace.read_file",
      input: { path: "/inputs/notes.md" },
    },
    {
      name: "workspace.write_file",
      input: { path: "/reports/report.md", content: "# Report\nImportant input.\n" },
    },
    {
      name: "presentation.present",
      input: {
        resources: [{ kind: "workspace_file", path: "/reports/report.md" }],
      },
    },
  ];

  // Execute
  const completedRun = await runtime.worker.startRun(run, {
    steps: script,
    finalContent: "Created /reports/report.md",
  });

  // Gather results
  const events = runtime.store.listEvents(run.id);
  const files = runtime.store.listWorkspaceFiles(run.workspace_id);
  const reportFiles = files.filter((f) => f.path.startsWith("/reports/"));
  const reportPath = reportFiles.length > 0 ? reportFiles[0].path : "<none>";
  const presentations = events.filter(
    (e) => e.type === "tool.completed" && (e.payload as any)?.name === "presentation.present",
  );

  // Print results (same shape as Python output)
  console.log(`Run id: ${completedRun.id}`);
  console.log(`Run status: ${completedRun.status}`);
  console.log(`Report path: ${reportPath}`);
  console.log(
    `Workspace files: ${files.map((f) => f.path).join(", ") || "(none)"}`,
  );
  console.log(`Presentations: ${presentations.length}`);
  console.log(`Events: ${events.length}`);

  // Print event types
  const eventTypes = [...new Set(events.map((e) => e.type))].sort();
  console.log(`Event types: ${eventTypes.join(", ")}`);

  // Verify acceptance criteria
  const requiredEvents = [
    "run.created",
    "run.started",
    "message.created",
    "message.delta",
    "message.completed",
    "run.completed",
  ];
  const missing = requiredEvents.filter((t) => !eventTypes.includes(t));
  if (missing.length > 0) {
    console.log(`\nWARNING: Missing required events: ${missing.join(", ")}`);
  } else {
    console.log(`\nAll required events present.`);
  }
}

main().catch((err) => {
  console.error("File report agent failed:", err);
  process.exit(1);
});
