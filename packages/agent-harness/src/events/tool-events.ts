import type { RunId, ThreadId, WorkspaceId, ToolCallId, ArtifactId, AgentToolCallResult } from "@aithru/agent-core";
import type { AgentEventWriter, AgentStreamEvent } from "@aithru/agent-stream";
import { ev } from "./event-input.js";
import { nextArtifactId } from "../internal/counters.js";

/**
 * Emit events from a tool result:
 * - workspace.file.created / workspace.file.deleted for workspaceChanges
 * - artifact.created for completed results
 * - tool.completed / tool.failed / tool.denied
 */
export async function* emitToolResult(
  writer: AgentEventWriter,
  runId: RunId,
  threadId: ThreadId | undefined,
  workspaceId: WorkspaceId,
  toolCallId: ToolCallId,
  toolName: string,
  toolResult: AgentToolCallResult,
): AsyncGenerator<AgentStreamEvent> {
  if (toolResult.workspaceChanges) {
    for (const change of toolResult.workspaceChanges) {
      yield await writer.write(ev({
        runId, threadId,
        type: change.operation === "deleted" ? "workspace.file.deleted" : "workspace.file.created",
        source: { kind: "workspace" },
        payload: { workspaceId, path: change.path, operation: change.operation },
      }));
    }
  }

  if (toolResult.status === "completed" && toolResult.output) {
    yield await writer.write(ev({
      runId, threadId, type: "artifact.created", source: { kind: "harness" },
      payload: { artifactId: nextArtifactId() as ArtifactId, type: "text", name: `tool-output-${toolName}` },
    }));
  }

  const eventType = toolResult.status === "completed" ? "tool.completed"
    : toolResult.status === "denied" ? "tool.denied" : "tool.failed";
  yield await writer.write(ev({
    runId, threadId, type: eventType, source: { kind: "tool" },
    redaction: toolResult.redaction,
    payload: { toolCallId, toolName, status: toolResult.status },
  }));
}
