import type { AgentRun, AgentStreamEvent } from "@aithru-agent/contracts";
import type { CapabilityRouter, ToolPrepareResult } from "@aithru-agent/capabilities";
import type { AgentToolCallRequest, AgentToolCallResult } from "@aithru-agent/capabilities";
import { AgentEventWriter } from "@aithru-agent/stream";
import type { AgentStore } from "@aithru-agent/persistence";
import { EVENT_TYPES } from "@aithru-agent/stream";
import { validateRunStatusTransition } from "@aithru-agent/contracts";

export interface RunLoopContext {
  run: AgentRun;
  store: AgentStore;
  eventWriter: AgentEventWriter;
  capabilityRouter: CapabilityRouter;
}

export interface ToolCallStep {
  id?: string;
  name: string;
  input: Record<string, unknown>;
  requireApproval?: boolean;
  autoApprove?: boolean;
}

export interface ToolCallResult {
  completed: boolean;
  approvalRequired: boolean;
  inputRequired?: boolean;
  approvalId?: string;
  result?: AgentToolCallResult;
}

export class RunLoop {
  constructor(private ctx: RunLoopContext) {}

  get threadId(): string | null {
    return this.ctx.run.thread_id || null;
  }

  get runId(): string {
    return this.ctx.run.id;
  }

  get workspaceId(): string {
    return this.ctx.run.workspace_id;
  }

  // ── Lifecycle ─────────────────────────────────────────────────────

  emitRunStarted(): AgentStreamEvent {
    validateRunStatusTransition(this.ctx.run.status as string, "running");
    const run = this.ctx.store.updateRun(this.runId, {
      status: "running",
    });
    this.ctx.run = run;
    return this.ctx.eventWriter.write(this.runId, this.threadId, EVENT_TYPES.RUN_STARTED, {
      status: run.status,
    });
  }

  emitRunCompleted(result?: {
    content?: string;
    workspace_paths?: string[];
    message_id?: string | null;
    thread_message_id?: string | null;
  }): AgentStreamEvent {
    validateRunStatusTransition(this.ctx.run.status as string, "completed");
    const run = this.ctx.store.updateRun(this.runId, {
      status: "completed",
      completed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      result: {
        content: result?.content || null,
        workspace_paths: result?.workspace_paths || [],
        message_id: result?.message_id ?? null,
        thread_message_id: result?.thread_message_id ?? null,
      },
    });
    this.ctx.run = run;
    return this.ctx.eventWriter.write(this.runId, this.threadId, EVENT_TYPES.RUN_COMPLETED, {
      result: run.result,
    });
  }

  emitRunFailed(error: { code: string; message: string }): AgentStreamEvent {
    validateRunStatusTransition(this.ctx.run.status as string, "failed");
    const run = this.ctx.store.updateRun(this.runId, {
      status: "failed",
      completed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      error,
    });
    this.ctx.run = run;
    return this.ctx.eventWriter.write(this.runId, this.threadId, EVENT_TYPES.RUN_FAILED, {
      error,
    });
  }

  // ── Message ───────────────────────────────────────────────────────

  emitMessageCreated(messageId: string, content: string): AgentStreamEvent {
    return this.ctx.eventWriter.write(this.runId, this.threadId, EVENT_TYPES.MESSAGE_CREATED, {
      message_id: messageId,
      content: "",
    });
  }

  emitMessageDelta(
    messageId: string,
    delta: string,
    contentSoFar: string,
  ): AgentStreamEvent {
    return this.ctx.eventWriter.write(this.runId, this.threadId, EVENT_TYPES.MESSAGE_DELTA, {
      message_id: messageId,
      delta,
      content: contentSoFar,
    });
  }

  emitMessageCompleted(
    messageId: string,
    content: string,
    options: { threadMessageId?: string | null } = {},
  ): AgentStreamEvent {
    const payload: Record<string, unknown> = {
      message_id: messageId,
      content,
    };
    if (options.threadMessageId) payload.thread_message_id = options.threadMessageId;
    return this.ctx.eventWriter.write(this.runId, this.threadId, EVENT_TYPES.MESSAGE_COMPLETED, payload);
  }

  // ── Tool Call ─────────────────────────────────────────────────────

  async executeToolCall(step: ToolCallStep): Promise<ToolCallResult> {
    const toolCallId =
      step.id ??
      `tc_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;

    const request: AgentToolCallRequest = {
      id: toolCallId,
      name: step.name,
      input: step.input,
      run_id: this.runId,
    };

    // 1. Propose
    this.ctx.eventWriter.write(
      this.runId,
      this.threadId,
      EVENT_TYPES.TOOL_PROPOSED,
      { tool_call_id: toolCallId, name: step.name, input: step.input },
    );

    // 2. Prepare (check policy)
    const prepared = await this.ctx.capabilityRouter.prepareToolCall(request, { run: this.ctx.run });
    if (!prepared.allowed) {
      this.ctx.eventWriter.write(
        this.runId,
        this.threadId,
        EVENT_TYPES.TOOL_DENIED,
        {
          tool_call_id: toolCallId,
          name: step.name,
          reason: prepared.reason,
        },
      );
      return {
        completed: true,
        approvalRequired: false,
        result: {
          id: toolCallId,
          name: step.name,
          output: null,
          error: {
            code: "TOOL_DENIED",
            message: prepared.reason || "Tool call denied by policy",
            retryable: false,
          },
        },
      };
    }

    // 3. Approval check — actually pause, not auto-resolve
    if (prepared.requires_approval && !step.autoApprove) {
      const approvalId = `aprv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;

      // Create approval in store
      this.ctx.store.createApproval({
        id: approvalId,
        run_id: this.runId,
        tool_call_id: toolCallId,
        tool_name: step.name,
        status: "pending",
        created_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      });

      // Emit approval.requested
      this.ctx.eventWriter.write(
        this.runId,
        this.threadId,
        EVENT_TYPES.APPROVAL_REQUESTED,
        {
          approval_id: approvalId,
          tool_call_id: toolCallId,
          name: step.name,
        },
      );

      // Transition run to waiting_approval
      validateRunStatusTransition(this.ctx.run.status as string, "waiting_approval");
      this.ctx.store.updateRun(this.runId, {
        status: "waiting_approval",
        current_approval_id: approvalId,
      });
      this.ctx.run = this.ctx.store.getRun(this.runId)!;

      // Emit run.paused
      this.ctx.eventWriter.write(
        this.runId,
        this.threadId,
        EVENT_TYPES.RUN_PAUSED,
        {
          reason: "approval_required",
          approval_id: approvalId,
        },
      );

      return { completed: false, approvalRequired: true, approvalId };
    }

    // 4. Execute (no approval needed)
    this.ctx.eventWriter.write(
      this.runId,
      this.threadId,
      EVENT_TYPES.TOOL_STARTED,
      { tool_call_id: toolCallId, name: step.name },
    );

    const result = await this.ctx.capabilityRouter.executeToolCall(request, { run: this.ctx.run });

    if (result.error) {
      this.ctx.eventWriter.write(
        this.runId,
        this.threadId,
        EVENT_TYPES.TOOL_FAILED,
        {
          tool_call_id: toolCallId,
          name: step.name,
          error: result.error,
        },
      );
    } else if (step.name === "ask_clarification") {
      const payload = inputRequestPayload(this.runId, toolCallId, result.output);
      validateRunStatusTransition(this.ctx.run.status as string, "waiting_input");
      const pausedRun = this.ctx.store.updateRun(this.runId, { status: "waiting_input" });
      this.ctx.run = pausedRun;
      this.ctx.eventWriter.write(
        this.runId,
        this.threadId,
        EVENT_TYPES.INPUT_REQUESTED,
        payload,
      );
      this.ctx.eventWriter.write(
        this.runId,
        this.threadId,
        EVENT_TYPES.RUN_PAUSED,
        {
          status: "waiting_input",
          pause_reason: "clarification_requested",
          ...payload,
        },
      );
      return { completed: false, approvalRequired: false, inputRequired: true, result };
    } else {
      this.ctx.eventWriter.write(
        this.runId,
        this.threadId,
        EVENT_TYPES.TOOL_COMPLETED,
        {
          tool_call_id: toolCallId,
          name: step.name,
          output: result.output,
        },
      );
    }

    return { completed: true, approvalRequired: false, result };
  }
}

function inputRequestPayload(
  runId: string,
  toolCallId: string,
  output: unknown,
): Record<string, unknown> {
  const payload = isRecord(output) ? output : {};
  const inputRequestId = stringValue(payload.input_request_id) ?? `clarify_${runId}_${toolCallId}`;
  return {
    ...payload,
    input_request_id: inputRequestId,
    tool_call_id: stringValue(payload.tool_call_id) ?? toolCallId,
    prompt: stringValue(payload.prompt) ?? "Input requested.",
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}
