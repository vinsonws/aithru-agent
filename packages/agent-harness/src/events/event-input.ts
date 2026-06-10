import type { RunId, ThreadId } from "@aithru/agent-core";
import type { AgentEventWriterInput } from "@aithru/agent-stream";

/**
 * Factory that builds AgentEventWriterInput from a simple options object.
 */
export function ev(input: {
  runId: RunId;
  threadId?: ThreadId;
  type: AgentEventWriterInput["type"];
  source: AgentEventWriterInput["source"];
  visibility?: "user" | "debug" | "audit";
  redaction?: "none" | "partial" | "full";
  summary?: string;
  payload: unknown;
}): AgentEventWriterInput {
  return {
    runId: input.runId,
    threadId: input.threadId,
    type: input.type,
    source: input.source,
    visibility: input.visibility ?? "user",
    redaction: input.redaction ?? "none",
    summary: input.summary,
    payload: input.payload,
    timestamp: new Date().toISOString(),
  };
}
