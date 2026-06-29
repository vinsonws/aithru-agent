import type { AgentStore } from "../persistence/protocols.js";
import { InMemoryStore } from "../persistence/store.js";
import { SqliteStore } from "../persistence/sqlite-store.js";
import { AgentEventWriter } from "../stream/writer.js";
import { ProductionCapabilityRouter } from "../capabilities/production-router.js";
import { ScriptedHarnessCore } from "../core/harness.js";
import { WorkerRunner } from "../worker/runner.js";

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
    ? await SqliteStore.create()
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
