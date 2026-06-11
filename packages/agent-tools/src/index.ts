import type {
  AgentToolDescriptor,
  AgentToolCallRequest,
  AgentToolCallResult,
  AgentToolKind,
  RunId,
  WorkspaceId,
  OrgId,
  UserId,
  ToolCallId,
  AgentExternalRunRef,
} from "@aithru/agent-core";
import type { AgentWorkspaceProvider, WriteWorkspaceFileInput } from "@aithru/agent-workspace";

// ── Run context ─────────────────────────────────────────────────────────────

export type AgentRunContext = {
  runId: RunId;
  threadId?: string;
  skillId?: string;
  workspaceId: WorkspaceId;
  actor: {
    actorType: "user" | "service" | "delegated" | "system";
    userId?: UserId;
    serviceId?: string;
    orgId: OrgId;
    scopes: string[];
    authzVersion?: number;
    delegation?: unknown;
  };
  requestId?: string;
  traceId?: string;
};

// ── Workflow capability types ────────────────────────────────────────────────

export type WorkflowCapabilityDescriptor = {
  key: string;
  version: string;
  displayName: string;
  description: string;
  agentToolName: string;
  inputSchema?: unknown;
  outputSchema?: unknown;
  riskLevel: AgentToolDescriptor["riskLevel"];
  requiredScopes: string[];
  approvalPolicy: AgentToolDescriptor["approvalPolicy"];
};

export type CreateWorkflowCapabilityRunInput = {
  capabilityKey: string;
  input: unknown;
  source: {
    kind: "agent_tool_call";
    agentRunId: string;
    toolCallId: string;
  };
  actor: {
    mode: "delegated_user" | "service";
    userId?: string;
    orgId: string;
  };
  purpose: string;
};

export type WorkflowCapabilityRunResult = {
  runId: string;
  status: "queued" | "running" | "waiting_approval" | "completed" | "failed" | "cancelled";
  output?: unknown;
  approvalId?: string;
  error?: { code: string; message: string; retryable?: boolean };
  correlationId?: string;
  traceId?: string;
};

export type WorkflowCapabilityRun = WorkflowCapabilityRunResult;

export type ResolveWorkflowCapabilityApprovalInput = {
  capabilityRunId: string;
  approvalId: string;
  decision: "approved" | "rejected";
  comment?: string;
};

export interface WorkflowCapabilityClient {
  listCapabilities(): Promise<WorkflowCapabilityDescriptor[]>;
  createCapabilityRun(input: CreateWorkflowCapabilityRunInput): Promise<WorkflowCapabilityRunResult>;
  getCapabilityRun(runId: string): Promise<WorkflowCapabilityRun>;
  resolveCapabilityApproval(input: ResolveWorkflowCapabilityApprovalInput): Promise<void>;
}

// ── Prepare result type ────────────────────────────────────────────────────

export type AgentToolPrepareResult =
  | {
      status: "ready";
      descriptor: AgentToolDescriptor;
      redaction: "none" | "partial" | "full";
    }
  | {
      status: "waiting_approval";
      descriptor: AgentToolDescriptor;
      approvalId?: string;
      output?: unknown;
      redaction: "none" | "partial" | "full";
    }
  | {
      status: "denied";
      error: { code: string; message: string; retryable?: boolean };
      redaction: "none" | "partial" | "full";
    };

// ── Adapter interface ───────────────────────────────────────────────────────

export type ResolveExternalApprovalInput = {
  toolName: string;
  externalRun: NonNullable<AgentToolCallResult["externalRun"]>;
  approvalId: string;
  decision: "approved" | "rejected";
  comment?: string;
};

export interface AgentToolAdapter {
  kind: AgentToolKind;
  listTools(context: AgentRunContext): Promise<AgentToolDescriptor[]>;
  callTool(
    request: AgentToolCallRequest,
    descriptor: AgentToolDescriptor,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;
  resolveExternalApproval?(
    input: ResolveExternalApprovalInput,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;
}

// ── Router interface ────────────────────────────────────────────────────────

export interface AithruCapabilityRouter {
  listTools(context: AgentRunContext): Promise<AgentToolDescriptor[]>;

  /**
   * Two-phase prepare: check policy (scopes, approval).  Never calls the adapter.
   * Returns "ready", "waiting_approval", or "denied".
   */
  prepareToolCall(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolPrepareResult>;

  /**
   * Two-phase execute: called only after prepare returned "ready" (or after
   * an approval was resolved).  Calls the adapter.
   */
  executeToolCall(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;

  /**
   * Convenience: prepare + execute in one call.  Kept for compatibility.
   */
  callTool(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;

  resolveExternalApproval?(
    input: ResolveExternalApprovalInput,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;
}

// ── Shared helpers ──────────────────────────────────────────────────────────

function checkScopes(match: AgentToolDescriptor, context: AgentRunContext): boolean {
  return match.requiredScopes.length === 0
    || context.actor.scopes.includes("*")
    || match.requiredScopes.every((s) => context.actor.scopes.includes(s));
}

function needsApproval(match: AgentToolDescriptor, request: AgentToolCallRequest): boolean {
  // Harness-resolved approvals bypass the check
  if (request.alreadyApproved === true && request.requestedBy === "harness") return false;
  if (match.approvalPolicy === "always") return true;
  if (match.approvalPolicy === "on_risk" && (match.riskLevel === "write" || match.riskLevel === "dangerous")) return true;
  return false;
}

function findDescriptor(
  adapters: AgentToolAdapter[],
  toolName: string,
  context: AgentRunContext,
): Promise<{ adapter: AgentToolAdapter; descriptor: AgentToolDescriptor } | null> {
  return (async () => {
    for (const adapter of adapters) {
      const descriptors = await adapter.listTools(context);
      const match = descriptors.find((d) => d.name === toolName);
      if (match) return { adapter, descriptor: match };
    }
    return null;
  })();
}

// ── Static router ───────────────────────────────────────────────────────────

export class StaticCapabilityRouter implements AithruCapabilityRouter {
  constructor(private adapters: AgentToolAdapter[]) {}

  async listTools(context: AgentRunContext): Promise<AgentToolDescriptor[]> {
    const results = await Promise.all(
      this.adapters.map((a) => a.listTools(context)),
    );
    return results.flat();
  }

  async prepareToolCall(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolPrepareResult> {
    const found = await findDescriptor(this.adapters, request.toolName, context);
    if (!found) {
      return {
        status: "denied",
        error: { code: "TOOL_NOT_FOUND", message: `Tool '${request.toolName}' is not available` },
        redaction: "none",
      };
    }

    if (!checkScopes(found.descriptor, context)) {
      return {
        status: "denied",
        error: {
          code: "AUTHZ_DENIED",
          message: `Missing required scopes: ${found.descriptor.requiredScopes.filter((s) => !context.actor.scopes.includes(s)).join(", ")}`,
        },
        redaction: "none",
      };
    }

    // Workflow capabilities handle their own approval — skip Agent-owned check.
    if (found.descriptor.kind !== "workflow_capability" && needsApproval(found.descriptor, request)) {
      return {
        status: "waiting_approval",
        descriptor: found.descriptor,
        output: { reason: `Tool '${request.toolName}' requires approval (risk: ${found.descriptor.riskLevel})` },
        redaction: "none",
      };
    }

    return { status: "ready", descriptor: found.descriptor, redaction: "none" };
  }

  async executeToolCall(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult> {
    const found = await findDescriptor(this.adapters, request.toolName, context);
    if (!found) {
      return {
        id: request.id,
        toolName: request.toolName,
        status: "denied",
        error: { code: "TOOL_NOT_FOUND", message: `Tool '${request.toolName}' is not available` },
        redaction: "none",
      };
    }

    // Quick scope re-check
    if (!checkScopes(found.descriptor, context)) {
      return {
        id: request.id,
        toolName: request.toolName,
        status: "denied",
        error: {
          code: "AUTHZ_DENIED",
          message: `Missing scopes: ${found.descriptor.requiredScopes.filter((s) => !context.actor.scopes.includes(s)).join(", ")}`,
        },
        redaction: "none",
      };
    }

    // If the caller is NOT harness-approved but the tool would need approval, block.
    // Workflow capabilities handle their own approval — skip for those.
    if (found.descriptor.kind !== "workflow_capability" && needsApproval(found.descriptor, request)) {
      return {
        id: request.id,
        toolName: request.toolName,
        status: "waiting_approval",
        output: { reason: `Tool '${request.toolName}' requires approval` },
        redaction: "none",
      };
    }

    return found.adapter.callTool(request, found.descriptor, context);
  }

  async callTool(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult> {
    const prepared = await this.prepareToolCall(request, context);
    if (prepared.status === "ready") {
      return this.executeToolCall(request, context);
    }
    if (prepared.status === "denied") {
      return {
        id: request.id,
        toolName: request.toolName,
        status: "denied",
        error: prepared.error,
        redaction: prepared.redaction,
      };
    }
    // waiting_approval
    return {
      id: request.id,
      toolName: request.toolName,
      status: "waiting_approval",
      output: prepared.output,
      redaction: prepared.redaction,
    };
  }

  async resolveExternalApproval(
    input: ResolveExternalApprovalInput,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult> {
    const found = await findDescriptor(this.adapters, input.toolName, context);
    if (!found || !found.adapter.resolveExternalApproval) {
      return {
        id: input.externalRun.capabilityRunId as ToolCallId,
        toolName: input.toolName,
        status: "failed",
        error: {
          code: "TOOL_FAILED",
          message: `Tool '${input.toolName}' cannot resolve external approvals`,
        },
        externalRun: input.externalRun,
        redaction: "none",
      };
    }
    return found.adapter.resolveExternalApproval(input, context);
  }
}

// ── Allowed-tools policy check ──────────────────────────────────────────────

export function applyAllowedToolsFilter(
  descriptors: AgentToolDescriptor[],
  allowedToolNames: string[],
): AgentToolDescriptor[] {
  if (allowedToolNames.length === 0) return [];
  return descriptors.filter((d) => allowedToolNames.includes(d.name));
}

// ── Workspace tool adapter ──────────────────────────────────────────────────

export class WorkspaceToolAdapter implements AgentToolAdapter {
  readonly kind = "local_tool" as AgentToolKind;

  constructor(private provider: AgentWorkspaceProvider) {}

  async listTools(_context: AgentRunContext): Promise<AgentToolDescriptor[]> {
    return [
      {
        name: "workspace.listFiles",
        description: "List files in the agent workspace",
        kind: "local_tool",
        requiredScopes: ["workspace:read"],
        riskLevel: "safe",
        approvalPolicy: "never",
        metadata: { provider: "workspace" },
      },
      {
        name: "workspace.readFile",
        description: "Read a file from the agent workspace",
        kind: "local_tool",
        requiredScopes: ["workspace:read"],
        riskLevel: "safe",
        approvalPolicy: "never",
        metadata: { provider: "workspace" },
      },
      {
        name: "workspace.writeFile",
        description: "Write a file to the agent workspace",
        kind: "local_tool",
        requiredScopes: ["workspace:write"],
        riskLevel: "write",
        approvalPolicy: "on_risk",
        metadata: { provider: "workspace" },
      },
      {
        name: "workspace.deleteFile",
        description: "Delete a file from the agent workspace",
        kind: "local_tool",
        requiredScopes: ["workspace:write"],
        riskLevel: "write",
        approvalPolicy: "on_risk",
        metadata: { provider: "workspace" },
      },
    ];
  }

  async callTool(
    request: AgentToolCallRequest,
    descriptor: AgentToolDescriptor,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult> {
    try {
      switch (request.toolName) {
        case "workspace.listFiles": {
          const path = (request.input as { path?: string }).path;
          const files = await this.provider.listFiles(context.workspaceId, path);
          return {
            id: request.id,
            toolName: request.toolName,
            status: "completed",
            output: files,
            redaction: "none",
          };
        }
        case "workspace.readFile": {
          const inputR = request.input as { path: string };
          const content = await this.provider.readFile(context.workspaceId, inputR.path);
          return {
            id: request.id,
            toolName: request.toolName,
            status: "completed",
            output: {
              content: typeof content.content === "string" ? content.content : "(binary)",
              mediaType: content.mediaType,
            },
            redaction: "partial",
          };
        }
        case "workspace.writeFile": {
          const inputW = request.input as { path: string; content: string; mediaType?: string };
          const writeInput: WriteWorkspaceFileInput = {
            workspaceId: context.workspaceId,
            path: inputW.path,
            content: inputW.content,
            mediaType: inputW.mediaType,
          };
          const file = await this.provider.writeFile(writeInput);
          return {
            id: request.id,
            toolName: request.toolName,
            status: "completed",
            output: file,
            workspaceChanges: [{ path: file.path, operation: "created" }],
            redaction: "none",
          };
        }
        case "workspace.deleteFile": {
          const inputD = request.input as { path: string };
          const deleted = await this.provider.deleteFile(context.workspaceId, inputD.path);
          return {
            id: request.id,
            toolName: request.toolName,
            status: "completed",
            output: { deleted: true },
            workspaceChanges: [{ path: deleted.path, operation: "deleted" }],
            redaction: "none",
          };
        }
        default:
          return {
            id: request.id,
            toolName: request.toolName,
            status: "failed",
            error: { code: "TOOL_FAILED", message: `Unknown workspace tool: ${request.toolName}` },
            redaction: "none",
          };
      }
    } catch (err) {
      return {
        id: request.id,
        toolName: request.toolName,
        status: "failed",
        error: { code: "TOOL_FAILED", message: err instanceof Error ? err.message : String(err) },
        redaction: "none",
      };
    }
  }
}

// ── Workflow capability adapter ────────────────────────────────────────────

export class WorkflowCapabilityAdapter implements AgentToolAdapter {
  readonly kind = "workflow_capability" as AgentToolKind;

  constructor(private client: WorkflowCapabilityClient) {}

  async listTools(_context: AgentRunContext): Promise<AgentToolDescriptor[]> {
    const capabilities = await this.client.listCapabilities();
    return capabilities.map((capability) => ({
      name: capability.agentToolName,
      description: capability.description,
      kind: "workflow_capability",
      inputSchema: capability.inputSchema,
      outputSchema: capability.outputSchema,
      requiredScopes: capability.requiredScopes,
      riskLevel: capability.riskLevel,
      approvalPolicy: capability.approvalPolicy,
      display: {
        name: capability.displayName,
        category: "Workflow Capability",
      },
      metadata: {
        capabilityKey: capability.key,
        capabilityVersion: capability.version,
        externalApprovalOwner: "workflow",
      },
    }));
  }

  async callTool(
    request: AgentToolCallRequest,
    descriptor: AgentToolDescriptor,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult> {
    const capabilityKey = descriptor.metadata?.capabilityKey;
    if (typeof capabilityKey !== "string") {
      return {
        id: request.id,
        toolName: request.toolName,
        status: "failed",
        error: { code: "TOOL_FAILED", message: `Missing capabilityKey for ${request.toolName}` },
        redaction: "none",
      };
    }

    const run = await this.client.createCapabilityRun({
      capabilityKey,
      input: request.input,
      source: {
        kind: "agent_tool_call",
        agentRunId: context.runId,
        toolCallId: request.id,
      },
      actor: {
        mode: context.actor.actorType === "service" ? "service" : "delegated_user",
        userId: context.actor.userId,
        orgId: context.actor.orgId,
      },
      purpose: `Agent tool call ${request.toolName}`,
    });

    const externalRun = {
      kind: "workflow_capability" as const,
      capabilityKey,
      capabilityVersion: descriptor.metadata?.capabilityVersion as string | undefined,
      capabilityRunId: run.runId,
      status: run.status,
      approvalId: run.approvalId,
      correlationId: run.correlationId,
      traceId: run.traceId,
    };

    if (run.status === "completed") {
      return {
        id: request.id,
        toolName: request.toolName,
        status: "completed",
        output: run.output,
        externalRun,
        redaction: "partial",
      };
    }

    if (run.status === "waiting_approval") {
      return {
        id: request.id,
        toolName: request.toolName,
        status: "waiting_approval",
        output: { reason: `Workflow capability '${capabilityKey}' requires approval` },
        externalRun,
        redaction: "partial",
      };
    }

    return {
      id: request.id,
      toolName: request.toolName,
      status: "failed",
      error: run.error ?? {
        code: "TOOL_FAILED",
        message: `Workflow capability '${capabilityKey}' ended with status ${run.status}`,
      },
      externalRun,
      redaction: "partial",
    };
  }

  async resolveExternalApproval(
    input: ResolveExternalApprovalInput,
    _context: AgentRunContext,
  ): Promise<AgentToolCallResult> {
    await this.client.resolveCapabilityApproval({
      capabilityRunId: input.externalRun.capabilityRunId,
      approvalId: input.approvalId,
      decision: input.decision,
      comment: input.comment,
    });

    const run = await this.client.getCapabilityRun(input.externalRun.capabilityRunId);
    const externalRun = {
      ...input.externalRun,
      status: run.status,
      approvalId: run.approvalId,
      correlationId: run.correlationId ?? input.externalRun.correlationId,
      traceId: run.traceId ?? input.externalRun.traceId,
    };

    if (run.status === "completed") {
      return {
        id: input.externalRun.capabilityRunId as ToolCallId,
        toolName: input.toolName,
        status: "completed",
        output: run.output,
        externalRun,
        redaction: "partial",
      };
    }

    return {
      id: input.externalRun.capabilityRunId as ToolCallId,
      toolName: input.toolName,
      status: run.status === "waiting_approval" ? "waiting_approval" : "failed",
      error: run.error,
      externalRun,
      redaction: "partial",
    };
  }
}
