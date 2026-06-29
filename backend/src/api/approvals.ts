import type { FastifyInstance } from "fastify";
import { getRuntime } from "../application/runtime.js";
import { EVENT_TYPES } from "../stream/events.js";

export function registerApprovalRoutes(app: FastifyInstance): void {
  // POST /api/approvals/:approval_id/resolve
  app.post(
    "/api/approvals/:approval_id/resolve",
    async (request, reply) => {
      const { approval_id } = request.params as any;
      const body = (request.body as any) || {};
      const decision: "approved" | "denied" = body.decision || "approved";
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

      return { resolved: true, approval_id: approval.id, decision };
    },
  );
}
