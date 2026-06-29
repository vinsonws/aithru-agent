import type { AgentStreamEvent } from "@aithru-agent/contracts";

interface AgentEventListStore {
  listEvents(runId: string): AgentStreamEvent[];
}

export class InMemoryAgentEventStore {
  constructor(private store: AgentEventListStore) {}

  async listByRun(runId: string): Promise<AgentStreamEvent[]> {
    return this.store.listEvents(runId);
  }
}
