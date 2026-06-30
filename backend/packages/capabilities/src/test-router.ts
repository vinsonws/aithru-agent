import type { CapabilityRouter, ToolPrepareResult } from "./router.js";
import type {
  AgentToolDescriptor,
  AgentToolCallRequest,
  AgentToolCallResult,
} from "./descriptors.js";
import type { RunContext } from "./policy.js";

interface TestCapabilityStore {
  getRun(id: string): { workspace_id: string } | undefined;
  listWorkspaceFiles(workspaceId: string): Array<{ path: string; size: number }>;
  readFile(workspaceId: string, path: string): { path: string; content: string } | undefined;
  writeFile(workspaceId: string, path: string, content: string): { path: string; version: number };
  deleteFile(workspaceId: string, path: string): boolean;
  createTodo(todo: {
    id: string;
    run_id: string;
    title: string;
    status: string;
    created_at: string;
    updated_at: string;
  }): { id: string; title: string; status: string };
  updateTodo(
    runId: string,
    todoId: string,
    patch: { title?: string; status?: string },
  ): { id: string; title: string; status: string };
}

const P0_TOOLS: AgentToolDescriptor[] = [
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
    required_scopes: ["workspace:write"],
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
    required_scopes: ["workspace:write"],
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
    required_scopes: ["todo:write"],
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
    required_scopes: ["todo:write"],
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
    name: "ask_clarification",
    description: "Ask the user for clarification before proceeding.",
    risk_level: "low",
    requires_approval: false,
    required_scopes: ["agent.input.write"],
    input_schema: {
      type: "object",
      properties: {
        question: { type: "string" },
        clarification_type: {
          type: "string",
          enum: ["missing_info", "ambiguous_requirement", "approach_choice", "risk_confirmation", "suggestion"],
        },
        context: { type: "string" },
        options: { type: "array", items: { type: "string" } },
      },
      required: ["question"],
    },
  },
  {
    name: "presentation.present",
    description: [
      "Present an existing workspace file to the user only when it is a final primary output or a file needed for user decision.",
      "Use for reports, previews, restore plans, summaries, or confirmation checklists.",
      "Do not present temporary files, logs, chunks, manifests, raw dumps, or routine intermediate edits.",
      "Add an open_panel preview effect only when the user asked to preview, the primary output is clearly previewable, or immediate confirmation is needed.",
    ].join(" "),
    risk_level: "low",
    requires_approval: false,
    required_scopes: ["presentation"],
    input_schema: {
      type: "object",
      properties: {
        resources: {
          type: "array",
          items: {
            type: "object",
            properties: {
              kind: { type: "string", enum: ["workspace_file"] },
              path: { type: "string" },
              title: { type: "string" },
              summary: { type: "string" },
              reason: { type: "string" },
              preferred_view: {
                type: "string",
                enum: ["html_preview", "markdown", "json", "image", "pdf", "source_text", "download"],
              },
              surfaces: {
                type: "array",
                items: {
                  type: "string",
                  enum: ["conversation", "side_panel", "approval_panel", "activity", "header"],
                },
              },
              effects: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    kind: { type: "string", enum: ["open_panel", "focus_presentation", "scroll_to", "highlight", "none"] },
                    panel: { type: "string", enum: ["preview", "files", "activity", "approvals", "trace"] },
                    mode: { type: "string", enum: ["soft", "assertive"] },
                  },
                },
              },
            },
            required: ["path"],
          },
        },
      },
      required: ["resources"],
    },
  },
];

export class TestCapabilityRouter implements CapabilityRouter {
  constructor(private store: TestCapabilityStore) {}

  async listTools(_ctx: RunContext): Promise<AgentToolDescriptor[]> {
    return P0_TOOLS;
  }

  async prepareToolCall(
    req: AgentToolCallRequest,
    _ctx?: RunContext,
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
    _ctx?: RunContext,
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

      case "ask_clarification": {
        const question = requiredString(input.question, "question");
        const context = optionalString(input.context);
        return {
          input_request_id: `clarify_${req.run_id}_${req.id}`,
          tool_call_id: req.id,
          prompt: question,
          reason: context ?? "The agent needs more information to proceed.",
          clarification_type: optionalString(input.clarification_type) ?? "missing_info",
          options: Array.isArray(input.options) ? input.options.map(String) : undefined,
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

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`Missing required input field: ${field}`);
  return value.trim();
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}
