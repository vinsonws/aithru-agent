import type {
  AgentRun,
  AgentMessage,
  AgentTodo,
  AgentArtifact,
  AgentSkill,
  RunId,
  MessageId,
  TodoId,
  WorkspaceId,
  ArtifactId,
  SkillId,
  ThreadId,
  OrgId,
  UserId,
  AgentToolCallRequest,
  ToolCallId,
  ApprovalId,
} from "@aithru/agent-core";
import { AgentError } from "@aithru/agent-core";
import type {
  AgentStreamEvent,
  AgentEventWriterInput,
} from "@aithru/agent-stream";
import { AgentEventWriter } from "@aithru/agent-stream";
import type { AgentSkillManifest } from "@aithru/agent-skills";
import type { AgentWorkspaceProvider } from "@aithru/agent-workspace";
import { applyAllowedToolsFilter } from "@aithru/agent-tools";
import type { AithruCapabilityRouter, AgentRunContext } from "@aithru/agent-tools";

// ── Model port ──────────────────────────────────────────────────────────────

export type AgentModelMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type AgentModelToolCall = {
  id: string;
  name: string;
  input: unknown;
};

export type AgentModelResult = {
  delta?: string;
  toolCalls?: AgentModelToolCall[];
  finished: boolean;
};

export interface AgentModelPort {
  start(messages: AgentModelMessage[], context: unknown): AsyncIterable<AgentModelResult>;
  cancel(): void;
}

// ── Skill resolver ──────────────────────────────────────────────────────────

export interface AgentSkillResolver {
  resolve(skillIdOrKey: string): Promise<AgentSkill | null>;
  resolveFromManifest(manifest: AgentSkillManifest, orgId: OrgId): Promise<AgentSkill>;
}

// ── Harness input types ─────────────────────────────────────────────────────

export type AgentHarnessRunInput = {
  orgId: OrgId;
  actorUserId: UserId;
  goal: string;
  threadId?: ThreadId;
  skillId?: SkillId;
  initialMessages?: AgentModelMessage[];
  /** Actor scopes for capability routing. Defaults to ["*"] (allow all). */
  scopes?: string[];
};

export type AgentHarnessResumeInput = {
  runId: RunId;
};

// ── Harness engine ports ────────────────────────────────────────────────────

export type AgentHarnessEnginePorts = {
  eventWriter: AgentEventWriter;
  workspaceProvider: AgentWorkspaceProvider;
  capabilityRouter: AithruCapabilityRouter;
  skillResolver: AgentSkillResolver;
  model: AgentModelPort;
};

// ── Engine interface ────────────────────────────────────────────────────────

export interface AgentHarnessEngine {
  run(input: AgentHarnessRunInput): AsyncIterable<AgentStreamEvent>;
  resume(input: AgentHarnessResumeInput): AsyncIterable<AgentStreamEvent>;
  cancel(runId: string): Promise<void>;
}

// ── Helper to build event input ─────────────────────────────────────────────

function ev(input: {
  runId: RunId;
  threadId?: ThreadId;
  type: AgentEventWriterInput["type"];
  source: AgentEventWriterInput["source"];
  visibility?: "user" | "debug" | "audit";
  redaction?: "none" | "partial" | "full";
  summary?: string;
  payload: unknown;
}): AgentEventWriterInput {
  return {
    runId: input.runId,
    threadId: input.threadId,
    type: input.type,
    source: input.source,
    visibility: input.visibility ?? "user",
    redaction: input.redaction ?? "none",
    summary: input.summary,
    payload: input.payload,
    timestamp: new Date().toISOString(),
  };
}

// ── Native harness engine ───────────────────────────────────────────────────

let runCounter = 0;
let messageCounter = 0;
let todoCounter = 0;
let toolCallCounter = 0;
let artifactCounter = 0;
let approvalCounter = 0;

export class NativeHarnessEngine implements AgentHarnessEngine {
  private cancelled = new Set<string>();
  private currentModelPort: AgentModelPort | null = null;

  constructor(private ports: AgentHarnessEnginePorts) {}

  async *run(input: AgentHarnessRunInput): AsyncIterable<AgentStreamEvent> {
    const writer = this.ports.eventWriter;
    writer.resetSequence();

    runCounter++;
    const runId = `run_${runCounter}` as RunId;

    // Create workspace
    const workspace = await this.ports.workspaceProvider.createWorkspace({
      orgId: input.orgId,
      threadId: input.threadId,
    });

    // ── run.created ──────────────────────────────────────────────────────
    yield await writer.write(
      ev({
        runId,
        threadId: input.threadId,
        type: "run.created",
        source: { kind: "harness" },
        payload: { status: "queued", source: "chat", workspaceId: workspace.id },
      }),
    );

    // ── run.started ──────────────────────────────────────────────────────
    yield await writer.write(
      ev({
        runId,
        threadId: input.threadId,
        type: "run.started",
        source: { kind: "harness" },
        payload: { status: "running" },
      }),
    );

    // Build run state
    const run: AgentRun = {
      id: runId,
      orgId: input.orgId,
      actorUserId: input.actorUserId,
      source: "chat",
      threadId: input.threadId,
      skillId: input.skillId,
      workspaceId: workspace.id,
      goal: input.goal,
      status: "running",
      startedAt: new Date().toISOString(),
    };

    // ── message.created ──────────────────────────────────────────────────
    messageCounter++;
    const msgId = `msg_${messageCounter}` as MessageId;
    yield await writer.write(
      ev({
        runId,
        threadId: input.threadId,
        type: "message.created",
        source: { kind: "harness" },
        payload: { messageId: msgId, role: "assistant" },
      }),
    );

    // ── todo.created ─────────────────────────────────────────────────────
    todoCounter++;
    const todoId = `todo_${todoCounter}` as TodoId;
    yield await writer.write(
      ev({
        runId,
        threadId: input.threadId,
        type: "todo.created",
        source: { kind: "harness" },
        payload: { todoId, title: "Process user request", status: "running", order: 1 },
      }),
    );

    // Build run context for capability router
    const runContext: AgentRunContext = {
      runId,
      threadId: input.threadId,
      skillId: input.skillId,
      workspaceId: run.workspaceId,
      actor: {
        actorType: "user",
        userId: input.actorUserId,
        orgId: input.orgId,
        scopes: input.scopes ?? ["*"],
      },
    };

    // Get available tools and apply skill-level allowlist policy when present.
    const allTools = await this.ports.capabilityRouter.listTools(runContext);
    const skill = input.skillId
      ? await this.ports.skillResolver.resolve(input.skillId)
      : null;
    if (input.skillId && !skill) {
      throw new AgentError("NOT_FOUND", `Skill not found: ${input.skillId}`);
    }
    const tools = skill
      ? applyAllowedToolsFilter(allTools, skill.allowedTools)
      : allTools;

    // Prepare model input
    const modelMessages = input.initialMessages ?? [
      { role: "user" as const, content: input.goal },
    ];

    // ── model.started ────────────────────────────────────────────────────
    yield await writer.write(
      ev({
        runId,
        threadId: input.threadId,
        type: "model.started",
        source: { kind: "model" },
        payload: {},
      }),
    );

    this.currentModelPort = this.ports.model;
    const modelResults = this.ports.model.start(modelMessages, { tools });

    try {
      for await (const result of modelResults) {
        if (this.cancelled.has(runId)) {
          yield await writer.write(
            ev({
              runId,
              threadId: input.threadId,
              type: "run.cancelled",
              source: { kind: "harness" },
              payload: { status: "cancelled" },
            }),
          );
          return;
        }

        // Emit message delta
        if (result.delta) {
          yield await writer.write(
            ev({
              runId,
              threadId: input.threadId,
              type: "message.delta",
              source: { kind: "model" },
              payload: { messageId: msgId, delta: result.delta },
            }),
          );
        }

        // Process tool calls
        if (result.toolCalls) {
          for (const tc of result.toolCalls) {
            toolCallCounter++;
            const toolCallId = `tc_${toolCallCounter}` as ToolCallId;

            // ── tool.proposed ────────────────────────────────────────────
            yield await writer.write(
              ev({
                runId,
                threadId: input.threadId,
                type: "tool.proposed",
                source: { kind: "tool" },
                summary: `Proposing ${tc.name}`,
                payload: { toolCallId, toolName: tc.name },
              }),
            );

            // ── tool.started ─────────────────────────────────────────────
            yield await writer.write(
              ev({
                runId,
                threadId: input.threadId,
                type: "tool.started",
                source: { kind: "tool" },
                payload: { toolCallId, toolName: tc.name },
              }),
            );

            // Execute through capability router
            const callRequest: AgentToolCallRequest = {
              id: toolCallId,
              toolName: tc.name,
              input: tc.input,
              requestedBy: "model",
            };

            const toolResult = await this.ports.capabilityRouter.callTool(
              callRequest,
              runContext,
            );

            if (toolResult.status === "waiting_approval") {
              approvalCounter++;
              const approvalId = toolResult.approvalId ?? (`approval_${approvalCounter}` as ApprovalId);

              yield await writer.write(
                ev({
                  runId,
                  threadId: input.threadId,
                  type: "approval.requested",
                  source: { kind: "approval" },
                  payload: {
                    approvalId,
                    toolCallId,
                    toolName: tc.name,
                    status: "pending",
                    output: toolResult.output,
                  },
                }),
              );

              yield await writer.write(
                ev({
                  runId,
                  threadId: input.threadId,
                  type: "run.paused",
                  source: { kind: "harness" },
                  payload: {
                    status: "waiting_approval",
                    approvalId,
                    toolCallId,
                    toolName: tc.name,
                  },
                }),
              );
              return;
            }

            // Handle workspace changes
            if (toolResult.workspaceChanges) {
              for (const change of toolResult.workspaceChanges) {
                yield await writer.write(
                  ev({
                    runId,
                    threadId: input.threadId,
                    type:
                      change.operation === "deleted"
                        ? "workspace.file.deleted"
                        : "workspace.file.created",
                    source: { kind: "workspace" },
                    payload: {
                      workspaceId: run.workspaceId,
                      path: change.path,
                      operation: change.operation,
                    },
                  }),
                );
              }
            }

            // ── artifact.created for any output ──────────────────────────
            if (toolResult.status === "completed" && toolResult.output) {
              artifactCounter++;
              const artId = `art_${artifactCounter}` as ArtifactId;
              yield await writer.write(
                ev({
                  runId,
                  threadId: input.threadId,
                  type: "artifact.created",
                  source: { kind: "harness" },
                  payload: {
                    artifactId: artId,
                    type: "text",
                    name: `tool-output-${tc.name}`,
                  },
                }),
              );
            }

            // ── tool.completed/failed/denied ─────────────────────────────
            const eventType =
              toolResult.status === "completed"
                ? "tool.completed"
                : toolResult.status === "denied"
                  ? "tool.denied"
                  : "tool.failed";
            yield await writer.write(
              ev({
                runId,
                threadId: input.threadId,
                type: eventType,
                source: { kind: "tool" },
                redaction: toolResult.redaction,
                payload: { toolCallId, toolName: tc.name, status: toolResult.status },
              }),
            );
          }
        }

        if (result.finished) break;
      }

      // ── todo.completed ─────────────────────────────────────────────────
      yield await writer.write(
        ev({
          runId,
          threadId: input.threadId,
          type: "todo.completed",
          source: { kind: "harness" },
          payload: { todoId, title: "Process user request", status: "done", order: 1 },
        }),
      );

      // ── message.completed ──────────────────────────────────────────────
      yield await writer.write(
        ev({
          runId,
          threadId: input.threadId,
          type: "message.completed",
          source: { kind: "harness" },
          payload: { messageId: msgId, role: "assistant" },
        }),
      );

      // ── run.completed ──────────────────────────────────────────────────
      yield await writer.write(
        ev({
          runId,
          threadId: input.threadId,
          type: "run.completed",
          source: { kind: "harness" },
          payload: { status: "completed" },
        }),
      );
    } catch (err) {
      // ── run.failed ─────────────────────────────────────────────────────
      yield await writer.write(
        ev({
          runId,
          threadId: input.threadId,
          type: "run.failed",
          source: { kind: "harness" },
          payload: {
            status: "failed",
            error: err instanceof Error ? err.message : String(err),
          },
        }),
      );
    }
  }

  async *resume(_input: AgentHarnessResumeInput): AsyncIterable<AgentStreamEvent> {
    yield {
      id: "" as unknown as never,
      runId: _input.runId,
      sequence: 0,
      timestamp: new Date().toISOString(),
      type: "run.failed",
      source: { kind: "harness" },
      visibility: "user",
      redaction: "none",
      summary: "Resume not yet implemented",
      payload: { status: "failed", error: "NOT_IMPLEMENTED" },
    };
  }

  async cancel(runId: string): Promise<void> {
    this.cancelled.add(runId);
    this.currentModelPort?.cancel();
  }
}

// ── Scripted model port ─────────────────────────────────────────────────────

type ScriptStep =
  | { type: "delta"; text: string }
  | { type: "tool"; name: string; input: unknown }
  | { type: "finish" };

export class ScriptedModelPort implements AgentModelPort {
  private cancelled = false;
  private steps: ScriptStep[];

  constructor(steps?: ScriptStep[]) {
    this.steps = steps ?? [
      { type: "delta", text: "I'll process your request step by step.\n\n" },
      { type: "delta", text: "First, let me check the workspace.\n\n" },
      {
        type: "tool",
        name: "workspace.listFiles",
        input: {},
      },
      { type: "delta", text: "\nDone! The workspace is ready.\n" },
      { type: "finish" },
    ];
  }

  async *start(
    _messages: AgentModelMessage[],
    _context: unknown,
  ): AsyncIterable<AgentModelResult> {
    for (const step of this.steps) {
      if (this.cancelled) break;

      // Simulate some delay
      await new Promise((r) => setTimeout(r, 10));

      switch (step.type) {
        case "delta":
          yield { delta: step.text, finished: false };
          break;
        case "tool":
          yield {
            toolCalls: [{ id: `tool_${Date.now()}`, name: step.name, input: step.input }],
            finished: false,
          };
          break;
        case "finish":
          yield { finished: true };
          break;
      }
    }
  }

  cancel(): void {
    this.cancelled = true;
  }
}
