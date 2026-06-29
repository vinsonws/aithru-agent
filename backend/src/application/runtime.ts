import type { AgentStore } from "@aithru-agent/persistence";
import { InMemoryStore } from "@aithru-agent/persistence";
import { SqliteStore } from "@aithru-agent/persistence";
import { AgentEventWriter } from "@aithru-agent/stream";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import { ScriptedHarnessCore } from "@aithru-agent/harness";
import { WorkerRunner } from "@aithru-agent/worker";

export interface AgentRuntime {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  capabilityRouter: ProductionCapabilityRouter;
  harness: ScriptedHarnessCore;
  worker: WorkerRunner;
}

let _runtime: AgentRuntime | null = null;

export async function createRuntime(dbPath?: string): Promise<AgentRuntime> {
  if (_runtime) return _runtime;

  const useSqlite = dbPath || process.env.DB_PATH;
  const store: AgentStore = useSqlite
    ? await SqliteStore.create(useSqlite)
    : new InMemoryStore();

  const eventWriter = new AgentEventWriter(store);
  const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter);
  const harness = new ScriptedHarnessCore({
    store,
    eventWriter,
    capabilityRouter,
  });
  const worker = new WorkerRunner({
    store,
    eventWriter,
    capabilityRouter,
  });

  _runtime = { store, eventWriter, capabilityRouter, harness, worker };
  return _runtime;
}

export function getRuntime(): AgentRuntime {
  if (!_runtime)
    throw new Error("Runtime not initialized. Call createRuntime() first.");
  return _runtime;
}
