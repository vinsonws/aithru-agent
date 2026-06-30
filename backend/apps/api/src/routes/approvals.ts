import type { FastifyInstance } from "fastify";
import { getRuntime } from "../runtime.js";
import { EVENT_TYPES } from "@aithru-agent/stream";
import type { AgentApproval } from "@aithru-agent/persistence";

function approvalResponse(approval: AgentApproval) {
  const resolved = approval.status === "approved" || approval.status === "denied";
  return {
    ...approval,
    tool_input: null,
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

      let approval;
      try {
        approval = runtime.store.resolveApproval(approval_id, decision);
      } catch {
        reply.code(404);
        return { error: "Approval not found" };
      }

      const run = runtime.store.getRun(approval.run_id);
      if (!run) {
        reply.code(404);
        return { error: "Run not found" };
      }

      // Emit approval resolved event
      runtime.eventWriter.write(
        approval.run_id,
        run.thread_id ?? null,
        EVENT_TYPES.APPROVAL_RESOLVED,
        {
          approval_id: approval.id,
          tool_call_id: approval.tool_call_id,
          name: approval.tool_name,
          decision,
        },
      );

      if (decision === "approved" && run.status === "waiting_approval" && run.current_approval_id === approval.id) {
        const resumed = runtime.store.updateRun(run.id, {
          status: "queued",
          current_approval_id: null,
        });
        runtime.eventWriter.write(
          run.id,
          run.thread_id ?? null,
          EVENT_TYPES.RUN_RESUMED,
          { status: "queued", resume_reason: "approval_resolved", approval_id: approval.id },
        );
        void runtime.scheduleRunExecution(resumed);
      }

      return approvalResponse(approval);
    },
  );
}
