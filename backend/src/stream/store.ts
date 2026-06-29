import { InMemoryStore } from "../persistence/store.js";
import type { AgentStreamEvent } from "../contracts/types.js";

export class InMemoryAgentEventStore {
  constructor(private store: InMemoryStore) {}

  async listByRun(runId: string): Promise<AgentStreamEvent[]> {
    return this.store.listEvents(runId);
  }
}
