import { InMemoryStore } from "@aithru-agent/persistence";
import type { AgentStreamEvent } from "@aithru-agent/contracts";

export class InMemoryAgentEventStore {
  constructor(private store: InMemoryStore) {}

  async listByRun(runId: string): Promise<AgentStreamEvent[]> {
    return this.store.listEvents(runId);
  }
}
