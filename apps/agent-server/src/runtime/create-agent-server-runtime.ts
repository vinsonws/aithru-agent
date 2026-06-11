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
import type { AgentSkillResolver } from "@aithru/agent-harness";
import type { AgentSkillManifest } from "@aithru/agent-skills";
import type { OrgId, AgentSkill } from "@aithru/agent-core";
import { InMemoryAgentServerStore } from "../store/in-memory-agent-server-store.js";
import { AgentRunController } from "./agent-run-controller.js";

export type AgentServerRuntime = {
  eventStore: InMemoryAgentEventStore;
  eventBus: InMemoryAgentEventBus;
  eventWriter: AgentEventWriter;
  workspaceProvider: InMemoryWorkspaceProvider;
  capabilityRouter: StaticCapabilityRouter;
  store: InMemoryAgentServerStore;
  runController: AgentRunController;
};

/**
 * Create a self-contained Agent server runtime with in-memory infrastructure.
 *
 * Creates shared singletons:
 * - Event store / bus / writer (shared across all runs)
 * - Workspace provider (shared)
 * - Capability router with workspace and search adapters (shared)
 * - Minimal skill resolver (returns null for all skills)
 * - Agent server store (in-memory projection)
 * - Run controller (manages per-run engines)
 */
export function createAgentServerRuntime(): AgentServerRuntime {
  const eventStore = new InMemoryAgentEventStore();
  const eventBus = new InMemoryAgentEventBus();
  const eventWriter = new AgentEventWriter(eventStore, eventBus);
  const workspaceProvider = new InMemoryWorkspaceProvider();

  const capabilityRouter = new StaticCapabilityRouter([
    new WorkspaceToolAdapter(workspaceProvider),
  ]);

  const skillResolver: AgentSkillResolver = {
    async resolve(_skillIdOrKey: string): Promise<AgentSkill | null> {
      return null;
    },
    async resolveFromManifest(
      _manifest: AgentSkillManifest,
      _orgId: OrgId,
    ): Promise<AgentSkill> {
      throw new Error("Skill manifest resolution not supported in dev server");
    },
  };

  const store = new InMemoryAgentServerStore();

  const runController = new AgentRunController(
    { eventWriter, workspaceProvider, capabilityRouter, skillResolver },
    store,
    eventBus,
  );

  return {
    eventStore,
    eventBus,
    eventWriter,
    workspaceProvider,
    capabilityRouter,
    store,
    runController,
  };
}
