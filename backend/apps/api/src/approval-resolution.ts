import { ProductionCapabilityRouter, runContext } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import {
  ensureToolCallRecordForApproval,
  toolResultFromRecord,
  updateToolCallRecord,
  LIMIT_CONTINUATION_INCREMENT,
  isLimitContinuationApproval,
  limitKindFromToolCallId,
} from "@aithru-agent/harness";
import type { AgentModelToolResult } from "@aithru-agent/model";
import type { AgentApproval, AgentStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";

export class ApprovalResolutionError extends Error {
  constructor(readonly code: "APPROVAL_NOT_FOUND" | "RUN_NOT_FOUND" | "PENDING_TOOL_CALL_NOT_FOUND") {
    super(code);
  }
}

export type ScheduleRunExecutionOptions = {
  wait?: boolean;
  toolResults?: AgentModelToolResult[];
};

export type ScheduleRunExecution = (
  run: AgentRun | string,
  options?: ScheduleRunExecutionOptions,
) => Promise<AgentRun | undefined>;

export function createApprovalResolver(deps: {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  capabilityRouter: ProductionCapabilityRouter;
  scheduleRunExecution: ScheduleRunExecution;
}) {
  return async (approvalId: string, decision: "approved" | "denied"): Promise<AgentApproval> => {
    const pendingApproval = deps.store.getApproval(approvalId);
    if (!pendingApproval) throw new ApprovalResolutionError("APPROVAL_NOT_FOUND");
    const run = deps.store.getRun(pendingApproval.run_id);
    if (!run) throw new ApprovalResolutionError("RUN_NOT_FOUND");

    const isLimitApproval = isLimitContinuationApproval(pendingApproval);
    const shouldResume = run.status === "waiting_approval" && run.current_approval_id === pendingApproval.id;

    let toolCall = null;
    if (!isLimitApproval && shouldResume) {
      toolCall = ensureToolCallRecordForApproval(deps.store, pendingApproval);
    }
    if (shouldResume && !isLimitApproval && !toolCall) {
      throw new ApprovalResolutionError("PENDING_TOOL_CALL_NOT_FOUND");
    }

    const wasPending = pendingApproval.status === "pending";
    const approval = wasPending
      ? deps.store.resolveApproval(approvalId, decision)
      : pendingApproval;
    if (wasPending) {
      const resolvedPayload: Record<string, unknown> = {
        approval_id: approval.id,
        tool_call_id: approval.tool_call_id,
        name: approval.tool_name,
        decision,
      };
      if (isLimitApproval) {
        const kind = limitKindFromToolCallId(approval.tool_call_id) ?? "model_requests";
        resolvedPayload.limit_kind = kind;
        resolvedPayload.limit_increment = { ...LIMIT_CONTINUATION_INCREMENT };
      }
      deps.eventWriter.write(
        approval.run_id,
        run.thread_id ?? null,
        EVENT_TYPES.APPROVAL_RESOLVED,
        resolvedPayload,
      );
    }

    if (!shouldResume || !wasPending) return approval;
    if (isLimitApproval) {
      return resolveLimitContinuationApproval(deps, run, approval, decision);
    }
    if (!toolCall) return approval;

    const resumed = deps.store.updateRun(run.id, {
      status: "running",
      current_approval_id: null,
    });
    deps.eventWriter.write(
      run.id,
      run.thread_id ?? null,
      EVENT_TYPES.RUN_RESUMED,
      { status: "running", resume_reason: "approval_resolved", approval_id: approval.id },
    );

    const toolResult = decision === "approved"
      ? await executeApprovedToolCall(deps, resumed, toolCall)
      : denyApprovedToolCall(deps, resumed, toolCall);
    void deps.scheduleRunExecution(deps.store.updateRun(run.id, { status: "queued" }), {
      toolResults: toolResult ? [toolResult] : [],
    });
    return approval;
  };
}

function resolveLimitContinuationApproval(
  deps: {
    store: AgentStore;
    eventWriter: AgentEventWriter;
    scheduleRunExecution: ScheduleRunExecution;
  },
  run: AgentRun,
  approval: AgentApproval,
  decision: "approved" | "denied",
): AgentApproval {
  if (decision === "denied") {
    const failed = deps.store.updateRun(run.id, {
      status: "failed",
      current_approval_id: null,
      completed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      error: { code: "LIMIT_CONTINUATION_DENIED", message: "Limit continuation denied by user" },
    });
    deps.eventWriter.write(
      run.id,
      run.thread_id ?? null,
      EVENT_TYPES.RUN_FAILED,
      { error: failed.error },
    );
    return approval;
  }

  deps.store.updateRun(run.id, {
    status: "running",
    current_approval_id: null,
  });
  deps.eventWriter.write(
    run.id,
    run.thread_id ?? null,
    EVENT_TYPES.RUN_RESUMED,
    { status: "running", resume_reason: "limit_continuation_approved", approval_id: approval.id },
  );
  void deps.scheduleRunExecution(deps.store.updateRun(run.id, { status: "queued" }), {
    toolResults: [],
  });
  return approval;
}

async function executeApprovedToolCall(
  deps: {
    store: AgentStore;
    eventWriter: AgentEventWriter;
    capabilityRouter: ProductionCapabilityRouter;
  },
  run: AgentRun,
  toolCall: NonNullable<ReturnType<typeof ensureToolCallRecordForApproval>>,
): Promise<AgentModelToolResult | null> {
  updateToolCallRecord(deps.store, toolCall.id, { status: "running" });
  deps.eventWriter.write(
    run.id,
    run.thread_id ?? null,
    EVENT_TYPES.TOOL_STARTED,
    { tool_call_id: toolCall.id, name: toolCall.tool_name },
  );
  const result = await deps.capabilityRouter.executeToolCall(
    {
      id: toolCall.id,
      name: toolCall.tool_name,
      input: toolCall.input,
      run_id: run.id,
    },
    runContext(run),
  );
  const updated = updateToolCallRecord(
    deps.store,
    toolCall.id,
    result.error
      ? { status: "failed", output: result.output, error: result.error }
      : { status: "completed", output: result.output, error: null },
  );
  deps.eventWriter.write(
    run.id,
    run.thread_id ?? null,
    result.error ? EVENT_TYPES.TOOL_FAILED : EVENT_TYPES.TOOL_COMPLETED,
    result.error
      ? { tool_call_id: toolCall.id, name: toolCall.tool_name, error: result.error }
      : { tool_call_id: toolCall.id, name: toolCall.tool_name, output: result.output },
  );
  return toolResultFromRecord(updated);
}

function denyApprovedToolCall(
  deps: {
    store: AgentStore;
    eventWriter: AgentEventWriter;
  },
  run: AgentRun,
  toolCall: NonNullable<ReturnType<typeof ensureToolCallRecordForApproval>>,
): AgentModelToolResult | null {
  const error = {
    code: "TOOL_DENIED",
    message: "Tool call denied by user approval decision",
    retryable: false,
  };
  const updated = updateToolCallRecord(deps.store, toolCall.id, {
    status: "denied",
    error,
  });
  deps.eventWriter.write(
    run.id,
    run.thread_id ?? null,
    EVENT_TYPES.TOOL_DENIED,
    { tool_call_id: toolCall.id, name: toolCall.tool_name, reason: "approval_denied" },
  );
  return toolResultFromRecord(updated);
}
