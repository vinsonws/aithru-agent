/**
 * Basic example: NativeHarnessEngine with ScriptedModelPort
 *
 * Demonstrates:
 * 1. Event infrastructure (InMemoryEventStore / EventBus / EventWriter)
 * 2. Workspace provider + tool adapters + capability router
 * 3. NativeHarnessEngine run() — full approval pause flow
 * 4. NativeHarnessEngine resume() — resolve approval and complete
 * 5. Workspace file read after resume
 */

import {
  AgentEventWriter,
  InMemoryAgentEventStore,
  InMemoryAgentEventBus,
} from "@aithru/agent-stream";
import { InMemoryWorkspaceProvider } from "@aithru/agent-workspace";
import {
  StaticCapabilityRouter,
  WorkspaceToolAdapter,
} from "@aithru/agent-tools";
import {
  NativeHarnessEngine,
  ScriptedModelPort,
} from "@aithru/agent-harness";
import type { AgentHarnessEnginePorts, AgentSkillResolver } from "@aithru/agent-harness";
import type { OrgId, UserId, RunId, WorkspaceId } from "@aithru/agent-core";
import type { AgentSkillManifest } from "@aithru/agent-skills";
import type { AgentSkill } from "@aithru/agent-core";

async function main() {
  console.log("=== Aithru Agent Harness — Approval + Resume Demo ===\n");

  // 1. Create event infrastructure
  const eventStore = new InMemoryAgentEventStore();
  const eventBus = new InMemoryAgentEventBus();
  const eventWriter = new AgentEventWriter(eventStore, eventBus);
  console.log("✓ Event infrastructure created");

  // 2. Subscribe to events
  eventBus.subscribe("run_1" as RunId, (event) => {
    if (event.type === "approval.requested") {
      console.log("  [bus]  → approval requested");
    }
    if (event.type === "approval.resolved") {
      console.log("  [bus]  → approval resolved");
    }
  });
  console.log("✓ Event bus subscribed");

  // 3. Create workspace provider
  const workspaceProvider = new InMemoryWorkspaceProvider();
  console.log("✓ Workspace provider created");

  // 4. Create tool adapters
  const workspaceTools = new WorkspaceToolAdapter(workspaceProvider);
  console.log("✓ Tool adapters created");

  // 5. Create capability router
  const capabilityRouter = new StaticCapabilityRouter([workspaceTools]);
  console.log("✓ Capability router created");

  // 6. Create skill resolver (minimal)
  const skillResolver: AgentSkillResolver = {
    async resolve(_skillIdOrKey: string): Promise<AgentSkill | null> {
      return null;
    },
    async resolveFromManifest(
      _manifest: AgentSkillManifest,
      _orgId: OrgId,
    ): Promise<AgentSkill> {
      throw new Error("Not implemented");
    },
  };

  // 7. Create model port — ScriptedModelPort will request workspace.writeFile
  const model = new ScriptedModelPort();
  console.log("✓ Scripted model port created");

  // 8. Create harness engine
  const ports: AgentHarnessEnginePorts = {
    eventWriter,
    workspaceProvider,
    capabilityRouter,
    skillResolver,
    model,
  };
  const engine = new NativeHarnessEngine(ports);
  console.log("✓ Native harness engine created\n");

  // ════════════════════════════════════════════════════════════════════
  // 9. Phase 1 — Run until approval pause
  // ════════════════════════════════════════════════════════════════════
  console.log("═══ Phase 1: run() — workspace.writeFile triggers approval ═══\n");

  let capturedRunId: RunId = "run_1" as RunId;
  const phase1Events: string[] = [];

  for await (const event of engine.run({
    orgId: "org_1" as OrgId,
    actorUserId: "user_1" as UserId,
    goal: "Analyze and write a report.",
  })) {
    phase1Events.push(`[${event.sequence}] ${event.type}`);
    capturedRunId = event.runId;

    if (event.type === "run.created") {
      const ws = (event.payload as { workspaceId: string }).workspaceId;
      console.log(`  ${event.type}  (workspace: ${ws})`);
    } else if (event.type === "message.delta") {
      const d = (event.payload as { delta: string }).delta;
      process.stdout.write(`  ${event.type}: "${d.trim()}"\n`);
    } else if (event.type === "approval.requested") {
      console.log(`  ${event.type} — tool needs approval`);
    } else if (event.type === "run.paused") {
      console.log(`  ${event.type} — waiting for approval`);
    } else if (event.type === "run.completed" || event.type === "run.failed") {
      console.log(`  ${event.type}`);
    } else {
      console.log(`  ${event.type}`);
    }
  }

  console.log(`\n→ Phase 1 complete (${phase1Events.length} events)`);
  console.log(`→ Run paused, waiting for approval\n`);

  // ════════════════════════════════════════════════════════════════════
  // 10. Phase 2 — Resume and complete
  // ════════════════════════════════════════════════════════════════════
  console.log("═══ Phase 2: resume() — approve and complete ═══\n");

  const phase2Events: string[] = [];
  for await (const event of engine.resume({ runId: capturedRunId })) {
    phase2Events.push(`[${event.sequence}] ${event.type}`);

    if (event.type === "approval.resolved") {
      console.log(`  ${event.type} — approved`);
    } else if (event.type === "run.resumed") {
      console.log(`  ${event.type}`);
    } else if (event.type === "message.delta") {
      const d = (event.payload as { delta: string }).delta;
      process.stdout.write(`  ${event.type}: "${d.trim()}"\n`);
    } else if (event.type === "model.completed") {
      console.log(`  ${event.type}`);
    } else if (event.type === "workspace.file.created") {
      const p = (event.payload as { path: string }).path;
      console.log(`  ${event.type}: ${p}`);
    } else if (event.type === "artifact.created") {
      console.log(`  ${event.type}`);
    } else if (event.type === "tool.completed") {
      console.log(`  ${event.type}`);
    } else if (event.type === "run.completed") {
      console.log(`  ${event.type}`);
    }
  }

  console.log(`\n→ Phase 2 complete (${phase2Events.length} events)`);
  console.log(`→ Run completed successfully\n`);

  // ════════════════════════════════════════════════════════════════════
  // 11. Verify — read the file that was written through the tool pipeline
  // ════════════════════════════════════════════════════════════════════
  console.log("═══ Verification: workspace file written through tool pipeline ═══\n");

  // Get the workspaceId from the first event's payload
  const storedEvents = await eventStore.listByRun(capturedRunId);
  const createdEvent = storedEvents.find((e) => e.type === "run.created");
  const workspaceId = (createdEvent?.payload as { workspaceId: string }).workspaceId;

  try {
    const file = await workspaceProvider.readFile(workspaceId, "/reports/result.md");
    console.log("File: /reports/result.md");
    console.log("Content:");
    console.log("---");
    console.log(file.content);
    console.log("---");
    console.log("\n✓ File was written through: model → harness → capabilityRouter → toolAdapter → workspaceProvider");
  } catch {
    console.log("✗ File not found — the tool pipeline may have failed");
  }

  // ════════════════════════════════════════════════════════════════════
  // 12. Verify event store
  // ════════════════════════════════════════════════════════════════════
  console.log("\n═══ Final state ═══\n");
  const allEvents = await eventStore.listByRun(capturedRunId);
  const sequences = allEvents.map((e) => e.sequence).sort((a, b) => a - b);
  const isStrictlyIncreasing = sequences.every(
    (s, i) => i === 0 || s > sequences[i - 1]!,
  );

  console.log(`Total events across both phases: ${allEvents.length}`);
  console.log(`Sequences strictly increasing: ${isStrictlyIncreasing}`);
  console.log(`Event types: ${[...new Set(allEvents.map((e) => e.type))].join(", ")}`);
  console.log("\n=== Example completed successfully ===");
}

main().catch((err) => {
  console.error("Example failed:", err);
  process.exit(1);
});
