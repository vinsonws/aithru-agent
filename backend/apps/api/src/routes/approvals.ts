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

      const pendingApproval = runtime.store.getApproval(approval_id);
      if (!pendingApproval) {
        reply.code(404);
        return { error: "Approval not found" };
      }

      const run = runtime.store.getRun(pendingApproval.run_id);
      if (!run) {
        reply.code(404);
        return { error: "Run not found" };
      }
      const shouldResume =
        decision === "approved" &&
        run.status === "waiting_approval" &&
        run.current_approval_id === pendingApproval.id;
      const approvedToolCall = shouldResume
        ? approvedToolCallFromEvents(runtime.store.listEvents(run.id), pendingApproval)
        : null;
      if (shouldResume && !approvedToolCall) {
        reply.code(409);
        return { error: "Approved tool call input not found" };
      }

      const approval = runtime.store.resolveApproval(approval_id, decision);

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

      if (approvedToolCall) {
        const resumed = runtime.store.updateRun(run.id, {
          status: "running",
          current_approval_id: null,
        });
        runtime.eventWriter.write(
          run.id,
          run.thread_id ?? null,
          EVENT_TYPES.RUN_RESUMED,
          { status: "running", resume_reason: "approval_resolved", approval_id: approval.id },
        );
        runtime.eventWriter.write(
          run.id,
          run.thread_id ?? null,
          EVENT_TYPES.TOOL_STARTED,
          { tool_call_id: approvedToolCall.id, name: approvedToolCall.name },
        );
        const result = await runtime.capabilityRouter.executeToolCall(
          {
            id: approvedToolCall.id,
            name: approvedToolCall.name,
            input: approvedToolCall.input,
            run_id: run.id,
          },
          { run: resumed },
        );
        runtime.eventWriter.write(
          run.id,
          run.thread_id ?? null,
          result.error ? EVENT_TYPES.TOOL_FAILED : EVENT_TYPES.TOOL_COMPLETED,
          result.error
            ? { tool_call_id: approvedToolCall.id, name: approvedToolCall.name, error: result.error }
            : { tool_call_id: approvedToolCall.id, name: approvedToolCall.name, output: result.output },
        );
        void runtime.scheduleRunExecution(runtime.store.updateRun(run.id, { status: "queued" }));
      }

      return approvalResponse(approval);
    },
  );
}

function approvedToolCallFromEvents(events: Array<{ type: string; payload?: unknown }>, approval: AgentApproval) {
  const event = [...events].reverse().find((candidate) => {
    const payload = isRecord(candidate.payload) ? candidate.payload : {};
    return candidate.type === EVENT_TYPES.TOOL_PROPOSED && payload.tool_call_id === approval.tool_call_id;
  });
  const payload = isRecord(event?.payload) ? event.payload : {};
  return payload.name === approval.tool_name && isRecord(payload.input)
    ? { id: approval.tool_call_id, name: approval.tool_name, input: payload.input }
    : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
