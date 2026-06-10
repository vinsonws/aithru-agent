import type {
  AgentRun, RunId, MessageId, TodoId, WorkspaceId, ArtifactId, ApprovalId, ToolCallId,
  AgentToolCallRequest, AgentErrorCode, ThreadId,
} from "@aithru/agent-core";
import { AgentError } from "@aithru/agent-core";
import type { AgentStreamEvent, AgentEventWriter } from "@aithru/agent-stream";
import type { AgentRunContext, AithruCapabilityRouter, AgentToolPrepareResult } from "@aithru/agent-tools";
import { applyAllowedToolsFilter } from "@aithru/agent-tools";
import type { AgentWorkspaceProvider } from "@aithru/agent-workspace";
import type { AgentModelPort, AgentModelResult, AgentModelMessage } from "../model/model-port.js";
import type { AgentSkillResolver } from "../skill/skill-resolver.js";
import type { AgentHarnessEngine, AgentHarnessRunInput, AgentHarnessResumeInput, AgentHarnessEnginePorts } from "./types.js";
import { ev } from "../events/event-input.js";
import type { PendingApproval } from "../approval/pending-approval.js";
import {
  nextRunId, nextMessageId, nextTodoId, nextToolCallId, nextArtifactId, nextApprovalId,
} from "../internal/counters.js";

export class NativeHarnessEngine implements AgentHarnessEngine {
  private cancelled = new Set<string>();
  private currentModelPort: AgentModelPort | null = null;
  private pendingApprovals = new Map<RunId, PendingApproval>();

  constructor(private ports: AgentHarnessEnginePorts) {}

  async *run(input: AgentHarnessRunInput): AsyncIterable<AgentStreamEvent> {
    const writer = this.ports.eventWriter;
    const runId = nextRunId() as RunId;

    try {
      const workspace = await this.ports.workspaceProvider.createWorkspace({
        orgId: input.orgId, threadId: input.threadId,
      });

      yield await writer.write(ev({
        runId, threadId: input.threadId,
        type: "run.created", source: { kind: "harness" },
        payload: { status: "queued", source: "chat", workspaceId: workspace.id },
      }));

      yield await writer.write(ev({
        runId, threadId: input.threadId,
        type: "run.started", source: { kind: "harness" },
        payload: { status: "running" },
      }));

      const run: AgentRun = {
        id: runId, orgId: input.orgId, actorUserId: input.actorUserId,
        source: "chat", threadId: input.threadId, skillId: input.skillId,
        workspaceId: workspace.id, goal: input.goal, status: "running",
        startedAt: new Date().toISOString(),
      };

      const msgId = nextMessageId() as MessageId;
      yield await writer.write(ev({
        runId, threadId: input.threadId,
        type: "message.created", source: { kind: "harness" },
        payload: { messageId: msgId, role: "assistant" },
      }));

      const todoId = nextTodoId() as TodoId;
      yield await writer.write(ev({
        runId, threadId: input.threadId,
        type: "todo.created", source: { kind: "harness" },
        payload: { todoId, title: "Process user request", status: "running", order: 1 },
      }));

      const runContext: AgentRunContext = {
        runId, threadId: input.threadId, skillId: input.skillId, workspaceId: run.workspaceId,
        actor: { actorType: "user", userId: input.actorUserId, orgId: input.orgId, scopes: input.scopes ?? ["*"] },
      };

      const allTools = await this.ports.capabilityRouter.listTools(runContext);
      const skill = input.skillId ? await this.ports.skillResolver.resolve(input.skillId) : null;
      if (input.skillId && !skill) {
        throw new AgentError("SKILL_NOT_FOUND", `Skill not found: ${input.skillId}`);
      }
      const tools = skill ? applyAllowedToolsFilter(allTools, skill.allowedTools) : allTools;
      const toolAllowedNames = new Set(tools.map((t) => t.name));

      const modelMessages = input.initialMessages ?? [{ role: "user" as const, content: input.goal }];

      yield await writer.write(ev({
        runId, threadId: input.threadId,
        type: "model.started", source: { kind: "model" }, payload: {},
      }));

      this.currentModelPort = this.ports.model;
      const modelResults = this.ports.model.start(modelMessages, { tools });
      const modelIterator = modelResults[Symbol.asyncIterator]();

      const paused = yield* this._runModelLoop({
        writer, runId, threadId: input.threadId, runContext,
        msgId, todoId, modelIterator, toolAllowedNames,
      });

      if (!paused) {
        yield* this._emitCompletion(writer, runId, input.threadId, msgId, todoId);
      }
    } catch (err) {
      yield* this._emitRunFailed(writer, runId, input.threadId, err);
    }
  }

  /**
   * Consume model results. Returns `true` if paused for approval.
   *
   * Event order (safe tool):
   *   tool.proposed → prepareToolCall → tool.started → executeToolCall → result events
   *
   * Event order (tool needing approval):
   *   tool.proposed → prepareToolCall → approval.requested → run.paused → return true
   */
  private async *_runModelLoop(ctx: {
    writer: AgentEventWriter; runId: RunId; threadId?: ThreadId;
    runContext: AgentRunContext; msgId: MessageId; todoId: TodoId;
    modelIterator: AsyncIterator<AgentModelResult>; toolAllowedNames: Set<string>;
  }): AsyncGenerator<AgentStreamEvent, boolean, undefined> {
    const { writer, runId, threadId, runContext, msgId, todoId, modelIterator, toolAllowedNames } = ctx;

    while (true) {
      const next = await modelIterator.next();
      if (next.done) break;
      const result = next.value;
      if (this.cancelled.has(runId)) {
        yield await writer.write(ev({
          runId, threadId, type: "run.cancelled", source: { kind: "harness" },
          payload: { status: "cancelled" },
        }));
        return false;
      }

      // Emit message delta
      if (result.delta) {
        yield await writer.write(ev({
          runId, threadId, type: "message.delta", source: { kind: "model" },
          payload: { messageId: msgId, delta: result.delta },
        }));
      }

      // Process tool calls
      if (result.toolCalls) {
        for (const tc of result.toolCalls) {
          // Skill policy: model is untrusted
          if (!toolAllowedNames.has(tc.name)) {
            const deniedId = nextToolCallId() as ToolCallId;
            yield await writer.write(ev({
              runId, threadId, type: "tool.denied", source: { kind: "tool" },
              summary: `Tool '${tc.name}' denied by skill policy`,
              payload: { toolCallId: deniedId, toolName: tc.name, status: "denied" },
            }));
            continue;
          }

          const toolCallId = nextToolCallId() as ToolCallId;

          // ── 1. tool.proposed ─────────────────────────────────────────────
          yield await writer.write(ev({
            runId, threadId, type: "tool.proposed", source: { kind: "tool" },
            summary: `Proposing ${tc.name}`,
            payload: { toolCallId, toolName: tc.name },
          }));

          const callRequest: AgentToolCallRequest = {
            id: toolCallId, toolName: tc.name, input: tc.input, requestedBy: "model",
          };

          // ── 2. prepareToolCall (policy check, NO adapter call) ────────────
          const prepared = await this.ports.capabilityRouter.prepareToolCall(callRequest, runContext);

          if (prepared.status === "denied") {
            yield await writer.write(ev({
              runId, threadId, type: "tool.denied", source: { kind: "tool" },
              payload: { toolCallId, toolName: tc.name, status: "denied", error: prepared.error },
            }));
            continue;
          }

          if (prepared.status === "waiting_approval") {
            const approvalId = nextApprovalId() as ApprovalId;
            this.pendingApprovals.set(runId, {
              runId, threadId, msgId, todoId,
              workspaceId: runContext.workspaceId,
              toolCallId, tc, runContext, approvalId,
              modelIterator, toolAllowedNames,
            });

            yield await writer.write(ev({
              runId, threadId, type: "approval.requested", source: { kind: "approval" },
              payload: { approvalId, toolCallId, toolName: tc.name, status: "pending", output: prepared.output },
            }));
            yield await writer.write(ev({
              runId, threadId, type: "run.paused", source: { kind: "harness" },
              payload: { status: "waiting_approval", approvalId, toolCallId, toolName: tc.name },
            }));
            return true; // paused
          }

          // ── 3. tool.started (only here — approved/ready, execution imminent) ──
          yield await writer.write(ev({
            runId, threadId, type: "tool.started", source: { kind: "tool" },
            payload: { toolCallId, toolName: tc.name },
          }));

          // ── 4. executeToolCall ──────────────────────────────────────────
          const toolResult = await this.ports.capabilityRouter.executeToolCall(callRequest, runContext);

          // ── 5. Result events ────────────────────────────────────────────
          yield* this._emitToolResult(writer, runId, threadId, runContext.workspaceId, toolCallId, tc.name, toolResult);
        }
      }

      if (result.finished) break;
    }
    return false;
  }

  /**
   * Emit workspace/artifact/tool-completion events from a tool result.
   */
  private async *_emitToolResult(
    writer: AgentEventWriter, runId: RunId, threadId: ThreadId | undefined,
    workspaceId: WorkspaceId, toolCallId: ToolCallId, toolName: string,
    toolResult: Awaited<ReturnType<AithruCapabilityRouter["callTool"]>>,
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

  private async *_emitCompletion(
    writer: AgentEventWriter, runId: RunId, threadId: ThreadId | undefined,
    msgId: MessageId, todoId: TodoId,
  ): AsyncGenerator<AgentStreamEvent> {
    yield await writer.write(ev({
      runId, threadId, type: "todo.completed", source: { kind: "harness" },
      payload: { todoId, title: "Process user request", status: "done", order: 1 },
    }));
    yield await writer.write(ev({
      runId, threadId, type: "message.completed", source: { kind: "harness" },
      payload: { messageId: msgId, role: "assistant" },
    }));
    yield await writer.write(ev({
      runId, threadId, type: "run.completed", source: { kind: "harness" },
      payload: { status: "completed" },
    }));
  }

  private async *_emitRunFailed(
    writer: AgentEventWriter, runId: RunId, threadId: ThreadId | undefined,
    err: unknown, codeOverride?: AgentErrorCode,
  ): AsyncGenerator<AgentStreamEvent> {
    const code = codeOverride ?? (err instanceof AgentError ? err.code : "MODEL_FAILED");
    const message = err instanceof Error ? err.message.replace(/^\[[^\]]+\]\s*/, "") : String(err);
    yield await writer.write(ev({
      runId, threadId, type: "run.failed", source: { kind: "harness" },
      payload: { status: "failed", error: { code, message, retryable: err instanceof AgentError ? err.retryable : false } },
    }));
  }

  /**
   * Resume a run paused for approval.
   *
   * Event order (approved):
   *   approval.resolved → run.resumed → tool.started → executeToolCall → result events → continue model → completion
   *
   * Event order (rejected):
   *   approval.resolved → tool.denied → run.failed
   */
  async *resume(input: AgentHarnessResumeInput): AsyncIterable<AgentStreamEvent> {
    const writer = this.ports.eventWriter;

    // Part D: unknown resume now goes through EventWriter
    const pending = this.pendingApprovals.get(input.runId);
    if (!pending) {
      const runId = input.runId;
      yield* this._emitRunFailed(
        writer, runId, undefined,
        new AgentError("NOT_FOUND", "No pending approval found for this run"),
      );
      return;
    }

    const { runId, threadId, msgId, todoId, toolCallId, tc, runContext } = pending;
    const approval = input.approval ?? { approvalId: pending.approvalId, decision: "approved" as const };
    if (approval.approvalId !== pending.approvalId) {
      yield* this._emitRunFailed(
        writer, runId, threadId,
        new AgentError("AUTHZ_DENIED", `Approval id does not match: ${approval.approvalId}`),
      );
      return;
    }

    // ── approval.resolved ──────────────────────────────────────────────────
    yield await writer.write(ev({
      runId, threadId, type: "approval.resolved", source: { kind: "approval" },
      payload: {
        approvalId: pending.approvalId, toolCallId, toolName: tc.name,
        decision: approval.decision, comment: approval.comment,
      },
    }));

    if (approval.decision === "rejected") {
      this.pendingApprovals.delete(runId);
      yield await writer.write(ev({
        runId, threadId, type: "tool.denied", source: { kind: "tool" },
        payload: { toolCallId, toolName: tc.name, status: "denied", reason: approval.comment },
      }));
      yield* this._emitRunFailed(
        writer, runId, threadId,
        new AgentError("TOOL_DENIED", `Tool '${tc.name}' rejected`),
      );
      return;
    }

    // ── run.resumed → tool.started → executeToolCall ───────────────────────
    yield await writer.write(ev({
      runId, threadId, type: "run.resumed", source: { kind: "harness" },
      payload: { status: "running" },
    }));

    yield await writer.write(ev({
      runId, threadId, type: "tool.started", source: { kind: "tool" },
      payload: { toolCallId, toolName: tc.name },
    }));

    const approvedRequest: AgentToolCallRequest = {
      id: toolCallId, toolName: tc.name, input: tc.input,
      requestedBy: "harness", alreadyApproved: true,
    };

    try {
      const toolResult = await this.ports.capabilityRouter.callTool(approvedRequest, runContext);
      yield* this._emitToolResult(writer, runId, threadId, runContext.workspaceId, toolCallId, tc.name, toolResult);

      // Continue model loop after tool completes
      const paused = yield* this._runModelLoop({
        writer, runId, threadId, runContext, msgId, todoId,
        modelIterator: pending.modelIterator,
        toolAllowedNames: pending.toolAllowedNames,
      });

      if (!paused) {
        yield* this._emitCompletion(writer, runId, threadId, msgId, todoId);
        this.pendingApprovals.delete(runId);
      }
    } catch (err) {
      this.pendingApprovals.delete(runId);
      yield* this._emitRunFailed(writer, runId, threadId, err);
    }
  }

  async cancel(runId: string): Promise<void> {
    this.cancelled.add(runId);
    this.currentModelPort?.cancel();
  }
}
