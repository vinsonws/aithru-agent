/**
 * Basic example: NativeHarnessEngine with ScriptedModelPort
 *
 * This demonstrates:
 * 1. InMemoryEventStore / EventBus / EventWriter
 * 2. InMemoryWorkspaceProvider
 * 3. WorkspaceToolAdapter + FakeSearchToolAdapter
 * 4. StaticCapabilityRouter
 * 5. NativeHarnessEngine with ScriptedModelPort
 * 6. Full event stream iteration
 * 7. Workspace file read after run
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
  FakeSearchToolAdapter,
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
  console.log("=== Aithru Agent Harness Basic Example ===\n");

  // 1. Create event infrastructure
  const eventStore = new InMemoryAgentEventStore();
  const eventBus = new InMemoryAgentEventBus();
  const eventWriter = new AgentEventWriter(eventStore, eventBus);
  console.log("✓ Event infrastructure created");

  // 2. Subscribe to events for demonstration
  const testRunId = "run_1" as RunId;
  const userEvents: string[] = [];
  eventBus.subscribe(testRunId, (event) => {
    if (event.visibility === "user") {
      userEvents.push(`${event.type}: ${event.summary ?? ""}`);
    }
  });
  console.log("✓ Event bus subscribed");

  // 3. Create workspace provider
  const workspaceProvider = new InMemoryWorkspaceProvider();
  console.log("✓ Workspace provider created");

  // 4. Create tool adapters
  const workspaceTools = new WorkspaceToolAdapter(workspaceProvider);
  const fakeSearch = new FakeSearchToolAdapter();
  console.log("✓ Tool adapters created");

  // 5. Create capability router
  const capabilityRouter = new StaticCapabilityRouter([workspaceTools, fakeSearch]);
  const tools = await capabilityRouter.listTools({
    runId: testRunId,
    workspaceId: "ws_1" as WorkspaceId,
    actor: {
      actorType: "user",
      orgId: "org_1" as OrgId,
      scopes: ["*"],
    },
  });
  console.log(`✓ Capability router created with ${tools.length} tools`);
  console.log(`  Tools: ${tools.map((t) => t.name).join(", ")}\n`);

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

  // 7. Create model port (scripted - no real LLM)
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

  // 9. Run the harness
  console.log("=== Running harness ===\n");
  const events: string[] = [];
  let capturedWorkspaceId = "";

  for await (const event of engine.run({
    orgId: "org_1" as OrgId,
    actorUserId: "user_1" as UserId,
    goal: "Analyze the project structure and write a report.",
  })) {
    const line = `[${event.sequence}] ${event.type}`;
    events.push(line);

    if (event.type === "run.created") {
      const p = event.payload as { workspaceId: string };
      capturedWorkspaceId = p.workspaceId;
      console.log(`  ${line} (workspace: ${p.workspaceId})`);
    } else if (event.type === "message.delta") {
      const p = event.payload as { delta: string };
      process.stdout.write(`  ${line}: "${p.delta}"`);
    } else if (
      event.type === "tool.completed" ||
      event.type === "tool.failed" ||
      event.type === "tool.denied"
    ) {
      console.log(`  ${line}`);
    } else if (
      event.type === "workspace.file.created" ||
      event.type === "workspace.file.updated"
    ) {
      const p = event.payload as { path: string };
      console.log(`  ${line}: ${p.path}`);
    } else if (
      event.type === "run.completed" ||
      event.type === "run.failed" ||
      event.type === "run.cancelled"
    ) {
      console.log(`  ${line}`);
    } else {
      console.log(`  ${line}`);
    }
  }

  console.log(`\n=== Run complete (${events.length} events) ===\n`);

  // 10. Direct workspace access
  console.log("=== Writing and reading workspace files directly ===\n");
  await workspaceProvider.writeFile({
    workspaceId: capturedWorkspaceId as WorkspaceId,
    path: "/reports/result.md",
    content: "# Analysis Result\n\nTask completed successfully.\n",
  });
  const file = await workspaceProvider.readFile(
    capturedWorkspaceId,
    "/reports/result.md",
  );
  console.log("File: /reports/result.md");
  console.log("Content:");
  console.log("---");
  console.log(file.content);
  console.log("---");

  // 11. Verify events were stored
  const storedEvents = await eventStore.listByRun(testRunId);
  console.log(`\n=== Event store has ${storedEvents.length} events ===`);

  const sequences = storedEvents.map((e) => e.sequence).sort((a, b) => a - b);
  const isStrictlyIncreasing = sequences.every(
    (s, i) => i === 0 || s > sequences[i - 1]!,
  );
  console.log(`Sequences strictly increasing: ${isStrictlyIncreasing}`);

  console.log("\n=== Example completed successfully ===");
}

main().catch((err) => {
  console.error("Example failed:", err);
  process.exit(1);
});
