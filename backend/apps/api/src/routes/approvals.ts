import type { FastifyInstance } from "fastify";
import { ApprovalResolutionError } from "../approval-resolution.js";
import { getRuntime } from "../runtime.js";
import { ensureToolCallRecordForApproval } from "@aithru-agent/harness";
import type { AgentApproval, AgentStore } from "@aithru-agent/persistence";
import { actorCanAccessOwnedResource, platformActorFromRequest } from "../platform-auth.js";

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
      const approval = runtime.store.getApproval(approval_id);
      if (!approval) {
        reply.code(404);
        return { error: "Approval not found" };
      }
      const run = runtime.store.getRun(approval.run_id);
      if (!run) {
        reply.code(404);
        return { error: "Run not found" };
      }
      if (!actorCanAccessOwnedResource(platformActorFromRequest(request), run)) {
        reply.code(403);
        return { error: "Forbidden" };
      }

      try {
        const resolved = await runtime.resolveApproval(approval_id, decision);
        return approvalResponse(resolved, runtime.store);
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
