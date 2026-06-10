import type { AgentStreamEvent } from "@aithru/agent-stream";
import type { AgentServerStore, AgentServerRunStatus, AgentServerApprovalStatus } from "../store/types.js";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

/**
 * Project an AgentStreamEvent into the AgentServerStore.
 * This builds an API-queryable view from the event stream.
 * The event stream itself (InMemoryAgentEventStore) remains the source of truth.
 */
export function projectEventIntoStore(event: AgentStreamEvent, store: AgentServerStore): void {
  const p = asRecord(event.payload);

  switch (event.type) {
    case "run.created": {
      const wsId = asString(p.workspaceId);
      store.setRun({
        id: event.runId,
        orgId: asString(p.orgId) as any ?? "org_1",
        actorUserId: asString(p.actorUserId) as any ?? "user_1",
        threadId: event.threadId,
        goal: asString(p.goal) ?? "",
        workspaceId: wsId as any,
        status: "queued",
        createdAt: event.timestamp,
        updatedAt: event.timestamp,
      });
      break;
    }

    case "run.started": {
      store.updateRun(event.runId, { status: "running", startedAt: event.timestamp }).catch(() => {});
      break;
    }

    case "run.paused": {
      const approvalId = asString(p.approvalId);
      store.updateRun(event.runId, {
        status: "waiting_approval",
        currentApprovalId: approvalId as any,
      }).catch(() => {});
      break;
    }

    case "run.resumed": {
      store.updateRun(event.runId, { status: "running", currentApprovalId: undefined }).catch(() => {});
      break;
    }

    case "run.completed": {
      store.updateRun(event.runId, { status: "completed", completedAt: event.timestamp }).catch(() => {});
      break;
    }

    case "run.failed": {
      store.updateRun(event.runId, {
        status: "failed",
        completedAt: event.timestamp,
        error: p.error,
      }).catch(() => {});
      break;
    }

    case "run.cancelled": {
      store.updateRun(event.runId, { status: "cancelled", completedAt: event.timestamp }).catch(() => {});
      break;
    }

    case "approval.requested": {
      const approvalId = asString(p.approvalId);
      const toolCallId = asString(p.toolCallId);
      const toolName = asString(p.toolName);
      if (approvalId) {
        store.upsertApproval({
          id: approvalId as any,
          runId: event.runId,
          threadId: event.threadId,
          toolCallId: toolCallId as any,
          toolName,
          status: "pending",
          payload: event.payload,
        }).catch(() => {});
      }
      break;
    }

    case "approval.resolved": {
      const approvalId = asString(p.approvalId);
      if (approvalId) {
        store.resolveApproval(
          approvalId as any,
          (p.decision as "approved" | "rejected") ?? "approved",
          asString(p.comment),
        ).catch(() => {});
      }
      break;
    }

    case "approval.expired": {
      const approvalId = asString(p.approvalId);
      if (approvalId) {
        store.upsertApproval({
          id: approvalId as any,
          runId: event.runId,
          status: "expired",
        }).catch(() => {});
      }
      break;
    }

    default:
      // Other events (message.*, todo.*, model.*, tool.*, workspace.*, artifact.*)
      // are not projected into the server store in this phase.
      break;
  }
}
