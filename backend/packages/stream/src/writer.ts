import { nanoid } from "nanoid";
import type { AgentStreamEvent, AgentStreamSource } from "@aithru-agent/contracts";
import type { AgentStore } from "../../../src/persistence/protocols.js";
import { VISIBILITY, REDACTION } from "./events.js";
import { redactPayload } from "./redaction.js";

function generateEventId(): string {
  return `evt_${nanoid(12)}`;
}

export class AgentEventWriter {
  constructor(private store: AgentStore) {}

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
    const event: AgentStreamEvent = {
      id: generateEventId(),
      run_id: runId,
      thread_id: threadId,
      sequence: this.store.listEvents(runId).length + 1,
      timestamp: new Date().toISOString().replace(/\.\d{3}/, ""),
      type,
      source: opts?.source || { kind: "system" },
      visibility: opts?.visibility || VISIBILITY.USER,
      redaction: opts?.redaction || REDACTION.NONE,
      summary: opts?.summary || null,
      payload: redactPayload(payload, opts?.redaction || REDACTION.NONE),
    };
    this.store.appendEvent(runId, event);
    return event;
  }
}
