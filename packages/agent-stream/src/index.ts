import type { RunId, ThreadId, EventId } from "@aithru/agent-core";

// ── Event type strings ──────────────────────────────────────────────────────

export type AgentStreamEventType =
  // Run lifecycle
  | "run.created"
  | "run.queued"
  | "run.started"
  | "run.paused"
  | "run.resumed"
  | "run.completed"
  | "run.failed"
  | "run.cancelled"
  // Message events
  | "message.created"
  | "message.delta"
  | "message.completed"
  | "message.failed"
  // Todo events
  | "todo.created"
  | "todo.updated"
  | "todo.completed"
  | "todo.blocked"
  | "todo.cancelled"
  // Model events
  | "model.started"
  | "model.delta"
  | "model.completed"
  | "model.failed"
  // Tool events
  | "tool.proposed"
  | "tool.started"
  | "tool.completed"
  | "tool.failed"
  | "tool.denied"
  // Approval events
  | "approval.requested"
  | "approval.resolved"
  | "approval.expired"
  // Workspace events
  | "workspace.file.created"
  | "workspace.file.updated"
  | "workspace.file.deleted"
  | "workspace.file.diff"
  | "workspace.snapshot.created"
  // Artifact events
  | "artifact.created"
  | "artifact.updated"
  | "artifact.finalized"
  | "artifact.exported"
  // Subagent events
  | "subagent.started"
  | "subagent.message"
  | "subagent.todo.updated"
  | "subagent.completed"
  | "subagent.failed"
  // Sandbox events
  | "sandbox.started"
  | "sandbox.stdout"
  | "sandbox.stderr"
  | "sandbox.file.changed"
  | "sandbox.completed"
  | "sandbox.failed"
  // Memory events
  | "memory.read"
  | "memory.written"
  | "memory.skipped";

export type AgentStreamSourceKind =
  | "harness"
  | "model"
  | "tool"
  | "subagent"
  | "sandbox"
  | "workspace"
  | "memory"
  | "approval"
  | "system";

export type AgentStreamVisibility = "user" | "debug" | "audit";

export type AgentStreamRedaction = "none" | "partial" | "full";

export type AgentStreamSource = {
  kind: AgentStreamSourceKind;
  id?: string;
  name?: string;
};

export type AgentStreamEvent = {
  id: EventId;
  runId: RunId;
  threadId?: ThreadId;
  sequence: number;
  timestamp: string;
  type: AgentStreamEventType;
  source: AgentStreamSource;
  visibility: AgentStreamVisibility;
  redaction: AgentStreamRedaction;
  summary?: string;
  payload: unknown;
};

// ── Event creation helper ───────────────────────────────────────────────────

export function createAgentStreamEvent(input: {
  runId: RunId;
  threadId?: ThreadId;
  sequence: number;
  type: AgentStreamEventType;
  source: AgentStreamSource;
  visibility?: AgentStreamVisibility;
  redaction?: AgentStreamRedaction;
  summary?: string;
  payload: unknown;
}): AgentStreamEvent {
  return {
    id: `${input.runId}:${input.sequence}` as EventId,
    runId: input.runId,
    threadId: input.threadId,
    sequence: input.sequence,
    timestamp: new Date().toISOString(),
    type: input.type,
    source: input.source,
    visibility: input.visibility ?? "user",
    redaction: input.redaction ?? "none",
    summary: input.summary,
    payload: input.payload,
  };
}

// ── Event store ─────────────────────────────────────────────────────────────

export interface AgentEventStore {
  append(event: AgentStreamEvent): Promise<void>;
  listByRun(runId: RunId): Promise<AgentStreamEvent[]>;
  listAfterSequence(runId: RunId, afterSequence: number): Promise<AgentStreamEvent[]>;
}

export class InMemoryAgentEventStore implements AgentEventStore {
  private events = new Map<RunId, AgentStreamEvent[]>();

  async append(event: AgentStreamEvent): Promise<void> {
    const list = this.events.get(event.runId) ?? [];
    list.push(event);
    this.events.set(event.runId, list);
  }

  async listByRun(runId: RunId): Promise<AgentStreamEvent[]> {
    return this.events.get(runId) ?? [];
  }

  async listAfterSequence(runId: RunId, afterSequence: number): Promise<AgentStreamEvent[]> {
    const list = this.events.get(runId) ?? [];
    return list.filter((e) => e.sequence > afterSequence);
  }
}

// ── Event bus ───────────────────────────────────────────────────────────────

export type AgentEventSubscriber = (event: AgentStreamEvent) => void;

export interface AgentEventBus {
  publish(event: AgentStreamEvent): void;
  subscribe(runId: RunId, subscriber: AgentEventSubscriber): void;
  unsubscribe(runId: RunId, subscriber: AgentEventSubscriber): void;
}

export class InMemoryAgentEventBus implements AgentEventBus {
  private subscribers = new Map<RunId, Set<AgentEventSubscriber>>();

  publish(event: AgentStreamEvent): void {
    const subs = this.subscribers.get(event.runId);
    if (subs) {
      for (const fn of subs) {
        fn(event);
      }
    }
  }

  subscribe(runId: RunId, subscriber: AgentEventSubscriber): void {
    const subs = this.subscribers.get(runId) ?? new Set();
    subs.add(subscriber);
    this.subscribers.set(runId, subs);
  }

  unsubscribe(runId: RunId, subscriber: AgentEventSubscriber): void {
    const subs = this.subscribers.get(runId);
    if (subs) {
      subs.delete(subscriber);
      if (subs.size === 0) {
        this.subscribers.delete(runId);
      }
    }
  }
}

// ── Event writer (append + publish) ─────────────────────────────────────────

export type AgentEventWriterInput = Omit<AgentStreamEvent, "id" | "sequence">;

export class AgentEventWriter {
  private sequences = new Map<RunId, number>();

  constructor(
    private store: AgentEventStore,
    private bus: AgentEventBus,
  ) {}

  currentSequence(runId: RunId): number {
    return this.sequences.get(runId) ?? 0;
  }

  async write(event: AgentEventWriterInput): Promise<AgentStreamEvent> {
    const seq = (this.sequences.get(event.runId) ?? 0) + 1;
    this.sequences.set(event.runId, seq);
    const full: AgentStreamEvent = {
      ...event,
      sequence: seq,
      id: `${event.runId}:${seq}` as EventId,
    };

    // Persist before publish
    await this.store.append(full);
    this.bus.publish(full);

    return full;
  }

  resetSequence(runId?: RunId): void {
    if (runId) {
      this.sequences.delete(runId);
    } else {
      this.sequences.clear();
    }
  }
}

// ── SSE format helper ───────────────────────────────────────────────────────

export function formatSseEvent(event: AgentStreamEvent): string {
  const data = JSON.stringify(event);
  return `id: ${event.runId}:${event.sequence}\nevent: agent.event\ndata: ${data}\n\n`;
}
