import type { CapabilityRouter, ToolPrepareResult } from "./router.js";
import type {
  AgentToolDescriptor,
  AgentToolCallRequest,
  AgentToolCallResult,
} from "./descriptors.js";
import { InMemoryStore } from "../persistence/store.js";

const P0_TOOLS: AgentToolDescriptor[] = [
  {
    name: "workspace.list_files",
    description: "List files in the workspace",
    risk_level: "low",
    requires_approval: false,
    input_schema: {},
  },
  {
    name: "workspace.read_file",
    description: "Read a file from the workspace",
    risk_level: "low",
    requires_approval: false,
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
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string" },
        content: { type: "string" },
      },
      required: ["path", "content"],
    },
  },
  {
    name: "workspace.patch_file",
    description: "Patch a file in the workspace",
    risk_level: "medium",
    requires_approval: false,
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string" },
        old_text: { type: "string" },
        new_text: { type: "string" },
      },
      required: ["path", "old_text", "new_text"],
    },
  },
  {
    name: "workspace.delete_file",
    description: "Delete a file from the workspace",
    risk_level: "high",
    requires_approval: true,
    input_schema: {
      type: "object",
      properties: { path: { type: "string" } },
      required: ["path"],
    },
  },
  {
    name: "todo.create",
    description: "Create a todo",
    risk_level: "low",
    requires_approval: false,
    input_schema: {
      type: "object",
      properties: {
        title: { type: "string" },
        status: { type: "string" },
      },
      required: ["title"],
    },
  },
  {
    name: "todo.update",
    description: "Update a todo",
    risk_level: "low",
    requires_approval: false,
    input_schema: {
      type: "object",
      properties: {
        id: { type: "string" },
        title: { type: "string" },
        status: { type: "string" },
      },
      required: ["id"],
    },
  },
  {
    name: "presentation.present",
    description: "Present a resource",
    risk_level: "low",
    requires_approval: false,
    input_schema: {
      type: "object",
      properties: {
        resources: {
          type: "array",
          items: { type: "object" },
        },
      },
    },
  },
];

export class TestCapabilityRouter implements CapabilityRouter {
  constructor(private store: InMemoryStore) {}

  async listTools(_runId: string): Promise<AgentToolDescriptor[]> {
    return P0_TOOLS;
  }

  async prepareToolCall(
    req: AgentToolCallRequest,
  ): Promise<ToolPrepareResult> {
    const tool = P0_TOOLS.find((t) => t.name === req.name);
    if (!tool) {
      return { allowed: false, requires_approval: false, reason: `Unknown tool: ${req.name}` };
    }
    return {
      allowed: true,
      requires_approval: tool.requires_approval,
    };
  }

  async executeToolCall(
    req: AgentToolCallRequest,
  ): Promise<AgentToolCallResult> {
    const tool = P0_TOOLS.find((t) => t.name === req.name);
    if (!tool) {
      return {
        id: req.id,
        name: req.name,
        output: null,
        error: {
          code: "UNKNOWN_TOOL",
          message: `Unknown tool: ${req.name}`,
          retryable: false,
        },
      };
    }

    try {
      const output = await this._execute(req);
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

  private async _execute(req: AgentToolCallRequest): Promise<unknown> {
    const input = req.input as Record<string, any>;

    switch (req.name) {
      case "workspace.list_files": {
        const run = this.store.getRun(req.run_id);
        if (!run) throw new Error(`Run ${req.run_id} not found`);
        const files = this.store.listWorkspaceFiles(run.workspace_id);
        return { files: files.map((f) => ({ path: f.path, size: f.size })) };
      }

      case "workspace.read_file": {
        const run = this.store.getRun(req.run_id);
        if (!run) throw new Error(`Run ${req.run_id} not found`);
        const file = this.store.readFile(run.workspace_id, input.path);
        if (!file) throw new Error(`File not found: ${input.path}`);
        return { path: file.path, content: file.content };
      }

      case "workspace.write_file": {
        const run = this.store.getRun(req.run_id);
        if (!run) throw new Error(`Run ${req.run_id} not found`);
        const file = this.store.writeFile(
          run.workspace_id,
          input.path,
          input.content,
        );
        return { path: file.path, version: file.version };
      }

      case "workspace.patch_file": {
        const run = this.store.getRun(req.run_id);
        if (!run) throw new Error(`Run ${req.run_id} not found`);
        const file = this.store.readFile(run.workspace_id, input.path);
        if (!file) throw new Error(`File not found: ${input.path}`);
        const newContent = file.content.replace(
          input.old_text,
          input.new_text,
        );
        this.store.writeFile(run.workspace_id, input.path, newContent);
        return { path: input.path, patched: true };
      }

      case "workspace.delete_file": {
        const run = this.store.getRun(req.run_id);
        if (!run) throw new Error(`Run ${req.run_id} not found`);
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
        return {
          id: updated.id,
          title: updated.title,
          status: updated.status,
        };
      }

      case "presentation.present": {
        return { presented: true, resources: input.resources || [] };
      }

      default:
        throw new Error(`Tool not implemented in test router: ${req.name}`);
    }
  }
}
