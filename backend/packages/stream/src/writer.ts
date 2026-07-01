import { nanoid } from "nanoid";
import type { AgentStreamEvent, AgentStreamSource } from "@aithru-agent/contracts";
import { VISIBILITY, REDACTION } from "./events.js";
import { redactPayload } from "./redaction.js";

export interface AgentEventStore {
  appendEvent(runId: string, event: AgentStreamEvent): void;
  listEvents(runId: string): AgentStreamEvent[];
  nextEventSequence?(runId: string): number;
}

function generateEventId(): string {
  return `evt_${nanoid(12)}`;
}

type AgentEventListener = (event: AgentStreamEvent) => void;

export class AgentEventWriter {
  private readonly listeners = new Map<string, Set<AgentEventListener>>();

  constructor(private store: AgentEventStore) {}

  subscribe(runId: string, listener: AgentEventListener): () => void {
    const listeners = this.listeners.get(runId) ?? new Set<AgentEventListener>();
    listeners.add(listener);
    this.listeners.set(runId, listeners);
    return () => {
      const current = this.listeners.get(runId);
      if (!current) return;
      current.delete(listener);
      if (current.size === 0) this.listeners.delete(runId);
    };
  }

  write(
    runId: string,
    threadId: string | null,
    type: string,
    payload: unknown,
    opts?: {
      source?: AgentStreamSource;
      visibility?: typeof VISIBILITY[keyof typeof VISIBILITY];
      redaction?: typeof REDACTION[keyof typeof REDACTION];
      summary?: string;
    },
  ): AgentStreamEvent {
    const sequence = this.store.nextEventSequence?.(runId) ?? this.store.listEvents(runId).length + 1;
    const event: AgentStreamEvent = {
      id: generateEventId(),
      run_id: runId,
      thread_id: threadId,
      sequence,
      timestamp: new Date().toISOString().replace(/\.\d{3}/, ""),
      type,
      source: opts?.source || { kind: "system" },
      visibility: opts?.visibility || VISIBILITY.USER,
      redaction: opts?.redaction || REDACTION.NONE,
      summary: opts?.summary || null,
      payload: redactPayload(payload, opts?.redaction || REDACTION.NONE),
    };
    this.store.appendEvent(runId, event);
    for (const listener of [...(this.listeners.get(runId) ?? [])]) {
      listener(event);
    }
    return event;
  }
}
