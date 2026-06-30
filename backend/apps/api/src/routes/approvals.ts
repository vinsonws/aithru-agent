import type { FastifyInstance } from "fastify";
import { ApprovalResolutionError } from "../approval-resolution.js";
import { getRuntime } from "../runtime.js";
import { ensureToolCallRecordForApproval } from "@aithru-agent/harness";
import type { AgentApproval, AgentStore } from "@aithru-agent/persistence";

function approvalResponse(approval: AgentApproval, store: AgentStore) {
  const resolved = approval.status === "approved" || approval.status === "denied";
  const toolCall = ensureToolCallRecordForApproval(store, approval);
  return {
    ...approval,
    tool_input: toolCall?.input ?? null,
    status: resolved ? "resolved" : approval.status,
    decision:
      approval.status === "approved"
        ? "approved"
        : approval.status === "denied"
          ? "rejected"
          : null,
    comment: null,
    metadata: null,
  };
}

export function registerApprovalRoutes(app: FastifyInstance): void {
  // POST /api/approvals/:approval_id/resolve
  app.post(
    "/api/approvals/:approval_id/resolve",
    async (request, reply) => {
      const { approval_id } = request.params as any;
      const body = (request.body as any) || {};
      const decision: "approved" | "denied" =
        body.decision === "rejected" ? "denied" : body.decision || "approved";
      const runtime = getRuntime();

      try {
        const approval = await runtime.resolveApproval(approval_id, decision);
        return approvalResponse(approval, runtime.store);
      } catch (err) {
        if (err instanceof ApprovalResolutionError) {
          if (err.code === "APPROVAL_NOT_FOUND") {
            reply.code(404);
            return { error: "Approval not found" };
          }
          if (err.code === "RUN_NOT_FOUND") {
            reply.code(404);
            return { error: "Run not found" };
          }
          reply.code(409);
          return { error: "Pending tool call input not found" };
        }
        throw err;
      }
    },
  );
}
