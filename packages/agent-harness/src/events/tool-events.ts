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

  if (toolResult.externalRun) {
    yield await writer.write(ev({
      runId,
      threadId,
      type: "external_run.created",
      source: { kind: "external" },
      redaction: toolResult.redaction,
      payload: {
        kind: toolResult.externalRun.kind,
        capabilityKey: toolResult.externalRun.capabilityKey,
        capabilityVersion: toolResult.externalRun.capabilityVersion,
        capabilityRunId: toolResult.externalRun.capabilityRunId,
        toolCallId,
        toolName,
        status: toolResult.externalRun.status,
        approvalId: toolResult.externalRun.approvalId,
        correlationId: toolResult.externalRun.correlationId,
        traceId: toolResult.externalRun.traceId,
      },
    }));

    if (toolResult.status === "completed") {
      yield await writer.write(ev({
        runId,
        threadId,
        type: "external_run.completed",
        source: { kind: "external" },
        redaction: toolResult.redaction,
        payload: {
          kind: toolResult.externalRun.kind,
          capabilityKey: toolResult.externalRun.capabilityKey,
          capabilityRunId: toolResult.externalRun.capabilityRunId,
          toolCallId,
          toolName,
          status: "completed",
          correlationId: toolResult.externalRun.correlationId,
        },
      }));
    }

    if (toolResult.status === "failed") {
      yield await writer.write(ev({
        runId,
        threadId,
        type: "external_run.failed",
        source: { kind: "external" },
        redaction: toolResult.redaction,
        payload: {
          kind: toolResult.externalRun.kind,
          capabilityKey: toolResult.externalRun.capabilityKey,
          capabilityRunId: toolResult.externalRun.capabilityRunId,
          toolCallId,
          toolName,
          status: "failed",
          correlationId: toolResult.externalRun.correlationId,
          error: toolResult.error,
        },
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
