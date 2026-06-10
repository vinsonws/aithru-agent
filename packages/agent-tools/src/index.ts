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

// ── Adapter interface ───────────────────────────────────────────────────────

export interface AgentToolAdapter {
  kind: AgentToolKind;
  listTools(context: AgentRunContext): Promise<AgentToolDescriptor[]>;
  callTool(
    request: AgentToolCallRequest,
    descriptor: AgentToolDescriptor,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;
}

// ── Router interface ────────────────────────────────────────────────────────

export interface AithruCapabilityRouter {
  listTools(context: AgentRunContext): Promise<AgentToolDescriptor[]>;

  callTool(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;
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

  async callTool(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult> {
    // Find first adapter that can handle this tool
    for (const adapter of this.adapters) {
      const descriptors = await adapter.listTools(context);
      const match = descriptors.find((d) => d.name === request.toolName);
      if (!match) continue;

      // ── Scope check ──────────────────────────────────────────────────
      const hasAllScopes = match.requiredScopes.length === 0
        || context.actor.scopes.includes("*")
        || match.requiredScopes.every((s) => context.actor.scopes.includes(s));

      if (!hasAllScopes) {
        return {
          id: request.id,
          toolName: request.toolName,
          status: "denied",
          error: {
            code: "AUTHZ_DENIED",
            message: `Missing required scopes: ${match.requiredScopes.filter((s) => !context.actor.scopes.includes(s)).join(", ")}`,
          },
          redaction: "none",
        };
      }

      // ── Approval policy check ────────────────────────────────────────
      const needsApproval = !request.alreadyApproved
        && (match.approvalPolicy === "always"
          || (match.approvalPolicy === "on_risk" && (match.riskLevel === "write" || match.riskLevel === "dangerous")));

      if (needsApproval) {
        // MVP: no approval gateway yet, so deny with waiting_approval
        return {
          id: request.id,
          toolName: request.toolName,
          status: "waiting_approval",
          output: { reason: `Tool '${request.toolName}' requires approval (risk: ${match.riskLevel})` },
          redaction: "none",
        };
      }

      return adapter.callTool(request, match, context);
    }

    return {
      id: request.id,
      toolName: request.toolName,
      status: "denied",
      error: {
        code: "TOOL_NOT_FOUND",
        message: `Tool '${request.toolName}' is not available`,
      },
      redaction: "none",
    };
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
  readonly kind = "workspace" as AgentToolKind;

  constructor(private provider: AgentWorkspaceProvider) {}

  async listTools(_context: AgentRunContext): Promise<AgentToolDescriptor[]> {
    return [
      {
        name: "workspace.listFiles",
        description: "List files in the agent workspace",
        kind: "workspace",
        requiredScopes: ["workspace:read"],
        riskLevel: "safe",
        approvalPolicy: "never",
      },
      {
        name: "workspace.readFile",
        description: "Read a file from the agent workspace",
        kind: "workspace",
        requiredScopes: ["workspace:read"],
        riskLevel: "safe",
        approvalPolicy: "never",
      },
      {
        name: "workspace.writeFile",
        description: "Write a file to the agent workspace",
        kind: "workspace",
        requiredScopes: ["workspace:write"],
        riskLevel: "write",
        approvalPolicy: "on_risk",
      },
      {
        name: "workspace.deleteFile",
        description: "Delete a file from the agent workspace",
        kind: "workspace",
        requiredScopes: ["workspace:write"],
        riskLevel: "write",
        approvalPolicy: "on_risk",
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
            workspaceChanges: [{ path: inputW.path, operation: "created" }],
            redaction: "none",
          };
        }
        case "workspace.deleteFile": {
          const inputD = request.input as { path: string };
          await this.provider.deleteFile(context.workspaceId, inputD.path);
          return {
            id: request.id,
            toolName: request.toolName,
            status: "completed",
            output: { deleted: true },
            workspaceChanges: [{ path: inputD.path, operation: "deleted" }],
            redaction: "none",
          };
        }
        default:
          return {
            id: request.id,
            toolName: request.toolName,
            status: "failed",
            error: {
              code: "TOOL_FAILED",
              message: `Unknown workspace tool: ${request.toolName}`,
            },
            redaction: "none",
          };
      }
    } catch (err) {
      return {
        id: request.id,
        toolName: request.toolName,
        status: "failed",
        error: {
          code: "TOOL_FAILED",
          message: err instanceof Error ? err.message : String(err),
        },
        redaction: "none",
      };
    }
  }
}

// ── Fake search tool adapter ────────────────────────────────────────────────

export class FakeSearchToolAdapter implements AgentToolAdapter {
  readonly kind = "subsystem_api" as AgentToolKind;

  async listTools(_context: AgentRunContext): Promise<AgentToolDescriptor[]> {
    return [
      {
        name: "fake.search",
        description: "Fake web search for testing",
        kind: "subsystem_api",
        requiredScopes: ["search:read"],
        riskLevel: "safe",
        approvalPolicy: "never",
      },
      {
        name: "fake.fetch",
        description: "Fake URL fetch for testing",
        kind: "subsystem_api",
        requiredScopes: ["fetch:read"],
        riskLevel: "safe",
        approvalPolicy: "never",
      },
    ];
  }

  async callTool(
    request: AgentToolCallRequest,
    _descriptor: AgentToolDescriptor,
    _context: AgentRunContext,
  ): Promise<AgentToolCallResult> {
    return {
      id: request.id,
      toolName: request.toolName,
      status: "completed",
      output: {
        result: `[fake] ${request.toolName} called with: ${JSON.stringify(request.input)}`,
      },
      redaction: "none",
    };
  }
}
