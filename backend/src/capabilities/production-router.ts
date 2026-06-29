import type { CapabilityRouter, ToolPrepareResult } from "./router.js";
import type { AgentToolDescriptor, AgentToolCallRequest, AgentToolCallResult } from "./descriptors.js";
import type { RunContext } from "./policy.js";
import { PolicyEngine, resolveSkillPolicy } from "./policy.js";
import type { AgentStore } from "../persistence/protocols.js";
import { AgentEventWriter } from "../stream/writer.js";
import { EVENT_TYPES, VISIBILITY } from "../stream/events.js";

// P1 production tool set (P0 tools + artifact)
const PRODUCTION_TOOLS: AgentToolDescriptor[] = [
  // workspace tools
  {
    name: "workspace.list_files",
    description: "List files in the workspace",
    risk_level: "low",
    requires_approval: false,
    required_scopes: ["workspace:read"],
    input_schema: {},
  },
  {
    name: "workspace.read_file",
    description: "Read a file from the workspace",
    risk_level: "low",
    requires_approval: false,
    required_scopes: ["workspace:read"],
    input_schema: {
      type: "object",
      properties: { path: { type: "string" } },
      required: ["path"],
    },
  },
  {
    name: "workspace.write_file",
    description: "Write a file to the workspace",
    risk_level: "medium",
    requires_approval: true,
    required_scopes: ["workspace:write"],
    input_schema: {
      type: "object",
      properties: { path: { type: "string" }, content: { type: "string" } },
      required: ["path", "content"],
    },
  },
  {
    name: "workspace.patch_file",
    description: "Patch a file in the workspace",
    risk_level: "medium",
    requires_approval: false,
    required_scopes: ["workspace:write"],
    input_schema: {
      type: "object",
      properties: { path: { type: "string" }, old_text: { type: "string" }, new_text: { type: "string" } },
      required: ["path", "old_text", "new_text"],
    },
  },
  {
    name: "workspace.delete_file",
    description: "Delete a file from the workspace",
    risk_level: "high",
    requires_approval: true,
    required_scopes: ["workspace:write"],
    input_schema: {
      type: "object",
      properties: { path: { type: "string" } },
      required: ["path"],
    },
  },
  // todo tools
  {
    name: "todo.create",
    description: "Create a todo",
    risk_level: "low",
    requires_approval: false,
    required_scopes: ["todo:write"],
    input_schema: {
      type: "object",
      properties: { title: { type: "string" }, status: { type: "string" } },
      required: ["title"],
    },
  },
  {
    name: "todo.update",
    description: "Update a todo",
    risk_level: "low",
    requires_approval: false,
    required_scopes: ["todo:write"],
    input_schema: {
      type: "object",
      properties: { id: { type: "string" }, title: { type: "string" }, status: { type: "string" } },
      required: ["id"],
    },
  },
  // artifact tools (NEW in P1)
  {
    name: "artifact.create",
    description: "Create a new artifact",
    risk_level: "low",
    requires_approval: false,
    required_scopes: ["artifact:write"],
    input_schema: {
      type: "object",
      properties: {
        title: { type: "string" },
        content_type: { type: "string" },
        content: { type: "string" },
      },
      required: ["title", "content_type"],
    },
  },
  {
    name: "artifact.finalize",
    description: "Finalize an artifact",
    risk_level: "low",
    requires_approval: false,
    required_scopes: ["artifact:write"],
    input_schema: {
      type: "object",
      properties: { artifact_id: { type: "string" } },
      required: ["artifact_id"],
    },
  },
  // presentation
  {
    name: "presentation.present",
    description: "Present a resource",
    risk_level: "low",
    requires_approval: false,
    required_scopes: ["presentation"],
    input_schema: {
      type: "object",
      properties: { resources: { type: "array", items: { type: "object" } } },
    },
  },
];

export class ProductionCapabilityRouter implements CapabilityRouter {
  constructor(
    private store: AgentStore,
    private eventWriter: AgentEventWriter,
  ) {}

  async listTools(ctx: RunContext): Promise<AgentToolDescriptor[]> {
    // In P1, all tools are available; P2+ will filter by skill config
    return PRODUCTION_TOOLS;
  }

  async prepareToolCall(
    req: AgentToolCallRequest,
    ctx: RunContext,
  ): Promise<ToolPrepareResult> {
    const tool = PRODUCTION_TOOLS.find((t) => t.name === req.name);
    if (!tool) {
      return {
        allowed: false,
        requires_approval: false,
        reason: `Unknown tool: ${req.name}`,
        audit_event_type: "tool.unknown",
      };
    }

    // Build policy engine with empty skill policy for now (no skills loaded)
    const engine = new PolicyEngine(
      { allowedTools: new Set(), deniedTools: new Set() },
      ctx.run,
    );

    const policyResult = engine.checkToolCall(tool, req);

    if (!policyResult.allowed) {
      // Emit audit event for denied tool
      this.eventWriter.write(
        req.run_id,
        ctx.run.thread_id || null,
        policyResult.audit_event_type || EVENT_TYPES.TOOL_DENIED,
        {
          tool_call_id: req.id,
          name: req.name,
          reason: policyResult.reason,
        },
        { visibility: VISIBILITY.AUDIT },
      );
    }

    return {
      allowed: policyResult.allowed,
      requires_approval: policyResult.requires_approval,
      reason: policyResult.reason,
      audit_event_type: policyResult.audit_event_type,
    };
  }

  async executeToolCall(
    req: AgentToolCallRequest,
    ctx: RunContext,
  ): Promise<AgentToolCallResult> {
    const tool = PRODUCTION_TOOLS.find((t) => t.name === req.name);
    if (!tool) {
      return {
        id: req.id,
        name: req.name,
        output: null,
        error: { code: "UNKNOWN_TOOL", message: `Unknown: ${req.name}`, retryable: false },
      };
    }

    try {
      const output = await this._execute(req, ctx);
      return { id: req.id, name: req.name, output };
    } catch (err: any) {
      return {
        id: req.id,
        name: req.name,
        output: null,
        error: {
          code: "TOOL_EXECUTION_ERROR",
          message: err.message || "Tool execution failed",
          retryable: false,
        },
      };
    }
  }

  private async _execute(req: AgentToolCallRequest, ctx: RunContext): Promise<unknown> {
    const input = req.input as Record<string, any>;
    const run = ctx.run;

    switch (req.name) {
      case "workspace.list_files": {
        const files = this.store.listWorkspaceFiles(run.workspace_id);
        return { files: files.map((f) => ({ path: f.path, size: f.size })) };
      }
      case "workspace.read_file": {
        const file = this.store.readFile(run.workspace_id, input.path);
        if (!file) throw new Error(`File not found: ${input.path}`);
        return { path: file.path, content: file.content };
      }
      case "workspace.write_file": {
        const file = this.store.writeFile(run.workspace_id, input.path, input.content);
        return { path: file.path, version: file.version };
      }
      case "workspace.patch_file": {
        const file = this.store.readFile(run.workspace_id, input.path);
        if (!file) throw new Error(`File not found: ${input.path}`);
        const newContent = file.content.replace(input.old_text, input.new_text);
        this.store.writeFile(run.workspace_id, input.path, newContent);
        return { path: input.path, patched: true };
      }
      case "workspace.delete_file": {
        const deleted = this.store.deleteFile(run.workspace_id, input.path);
        return { path: input.path, deleted };
      }
      case "todo.create": {
        const todo = this.store.createTodo({
          id: `todo_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
          run_id: req.run_id,
          title: input.title,
          status: input.status || "pending",
          created_at: new Date().toISOString().replace(/\.\d{3}/, ""),
          updated_at: new Date().toISOString().replace(/\.\d{3}/, ""),
        });
        return { id: todo.id, title: todo.title, status: todo.status };
      }
      case "todo.update": {
        const updated = this.store.updateTodo(req.run_id, input.id, {
          title: input.title,
          status: input.status,
        });
        return { id: updated.id, title: updated.title, status: updated.status };
      }
      case "artifact.create": {
        const artifact = this.store.createArtifact({
          id: `art_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
          run_id: req.run_id,
          title: input.title,
          content_type: input.content_type,
          content: input.content || "",
          status: "draft",
          created_at: new Date().toISOString().replace(/\.\d{3}/, ""),
          updated_at: new Date().toISOString().replace(/\.\d{3}/, ""),
        });
        return { id: artifact.id, title: artifact.title, status: artifact.status };
      }
      case "artifact.finalize": {
        const artifact = this.store.finalizeArtifact(input.artifact_id);
        return { id: artifact.id, status: artifact.status };
      }
      case "presentation.present": {
        return { presented: true, resources: input.resources || [] };
      }
      default:
        throw new Error(`Tool not implemented: ${req.name}`);
    }
  }
}
