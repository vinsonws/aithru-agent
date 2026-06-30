import type { CapabilityRouter, ToolPrepareResult } from "./router.js";
import type { AgentToolDescriptor, AgentToolCallRequest, AgentToolCallResult } from "./descriptors.js";
import type { RunContext, SkillPolicy } from "./policy.js";
import type { AgentStreamEvent } from "@aithru-agent/contracts";
import { PolicyEngine, resolveSkillPolicy } from "./policy.js";
import { activeSkillKeysFromEvents } from "./skill-state.js";
import type { SkillResolver } from "@aithru-agent/skills";
import { AgentEventWriter, EVENT_TYPES, VISIBILITY } from "@aithru-agent/stream";

interface CapabilityStore {
  listWorkspaceFiles(workspaceId: string): Array<{ path: string; size: number }>;
  listEvents(runId: string): AgentStreamEvent[];
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
  // presentation
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

export class ProductionCapabilityRouter implements CapabilityRouter {
  constructor(
    private store: CapabilityStore,
    private eventWriter: AgentEventWriter,
    private skillResolver?: SkillResolver,
  ) {}

  async listTools(ctx: RunContext): Promise<AgentToolDescriptor[]> {
    const policy = this.skillPolicyForRun(ctx.run);
    if (!policy) return PRODUCTION_TOOLS;
    return PRODUCTION_TOOLS.filter((tool) => {
      if (policy.deniedTools.has(tool.name)) return false;
      if (policy.allowedTools.size > 0 && !policy.allowedTools.has(tool.name)) return false;
      return true;
    });
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

    const policy = this.skillPolicyForRun(ctx.run) ?? { allowedTools: new Set<string>(), deniedTools: new Set<string>() };
    const engine = new PolicyEngine(policy, ctx.run);

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
        if (shouldAutoPresentWrittenFile(run.task_msg, file.path)) {
          this.presentWorkspaceFile(
            req,
            run,
            { path: file.path, surfaces: ["conversation"] },
            0,
            "tool",
          );
        }
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
        const presentations = presentationRequests(input).map((resource, index) =>
          this.presentWorkspaceFile(req, run, resource, index),
        );
        return { presentations, rejected_requests: [] };
      }
      default:
        throw new Error(`Tool not implemented: ${req.name}`);
    }
  }

  private presentWorkspaceFile(
    req: AgentToolCallRequest,
    run: RunContext["run"],
    resource: Record<string, unknown>,
    index: number,
    createdBy: "model_request" | "tool" = "model_request",
  ) {
    const kind = optionalString(resource.kind) ?? "workspace_file";
    if (kind !== "workspace_file") throw new Error(`Unsupported presentation resource: ${kind}`);
    const requestedPath = requiredString(resource.path, "path");
    const file = this.store.readFile(run.workspace_id, requestedPath);
    if (!file) throw new Error(`File not found: ${requestedPath}`);

    const availableViews = viewsForPath(file.path);
    const requestedView = optionalString(resource.preferred_view);
    const preferredView = requestedView && availableViews.includes(requestedView)
      ? requestedView
      : availableViews[0];
    const presentation = {
      id: presentationId(req.run_id, file.path, index),
      run_id: req.run_id,
      thread_id: run.thread_id ?? null,
      status: "ready",
      priority: optionalString(resource.priority) ?? "normal",
      title: optionalString(resource.title) ?? fileName(file.path),
      summary: optionalString(resource.summary),
      reason: optionalString(resource.reason),
      resource: { kind: "workspace_file", path: file.path },
      surfaces: allowedStrings(resource.surfaces, PRESENTATION_SURFACES, ["conversation"]),
      preferred_view: preferredView,
      available_views: availableViews,
      effects: allowedEffects(resource.effects),
      actions: actionsForView(preferredView),
      metadata: { workspace_id: run.workspace_id },
      source: {
        created_by: createdBy,
        tool_call_id: req.id,
        tool_name: req.name,
      },
    };
    this.eventWriter.write(
      req.run_id,
      run.thread_id ?? null,
      "presentation.created",
      { presentation },
      { source: { kind: "tool", id: req.id, name: req.name } },
    );
    return presentation;
  }

  private skillPolicyForRun(
    run: { id: string; org_id: string; actor_user_id: string },
  ): SkillPolicy | null {
    if (!this.skillResolver) return null;
    const keys = activeSkillKeysFromEvents(this.store.listEvents(run.id));
    const configs = keys
      .map((key) => this.skillResolver!.resolve(key, run.org_id, run.actor_user_id))
      .filter((skill): skill is NonNullable<typeof skill> => skill !== null)
      .map((skill) => ({
        allowed_tools: skill.allowed_tools,
        denied_tools: skill.denied_tools,
      }));
    return configs.length ? resolveSkillPolicy(configs) : null;
  }
}

const PRESENTATION_SURFACES = ["conversation", "side_panel", "approval_panel", "activity", "header"];
const PRESENTATION_EFFECTS = ["open_panel", "focus_presentation", "scroll_to", "highlight", "none"];
const PRESENTATION_PANELS = ["preview", "files", "activity", "approvals", "trace"];

function presentationRequests(input: Record<string, unknown>): Array<Record<string, unknown>> {
  if (!Array.isArray(input.resources)) throw new Error("Missing required input field: resources");
  return input.resources.map((resource) => {
    if (!resource || typeof resource !== "object" || Array.isArray(resource)) {
      throw new Error("Invalid presentation resource");
    }
    return resource as Record<string, unknown>;
  });
}

function viewsForPath(path: string): string[] {
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "html" || ext === "htm") return ["html_preview", "source_text", "download"];
  if (ext === "md" || ext === "markdown") return ["markdown", "source_text", "download"];
  if (ext === "json") return ["json", "source_text", "download"];
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext ?? "")) return ["image", "download"];
  if (ext === "pdf") return ["pdf", "download"];
  return ["source_text", "download"];
}

function shouldAutoPresentWrittenFile(taskMsg: string, path: string): boolean {
  if (isAuxiliaryPath(path)) return false;
  const text = taskMsg.toLowerCase();
  return presentablePathMentions(path).some((candidate) => text.includes(candidate.toLowerCase()));
}

function presentablePathMentions(path: string): string[] {
  const normalized = path.replace(/^\/+/, "");
  return [path, normalized, fileName(path)].filter(Boolean);
}

function isAuxiliaryPath(path: string): boolean {
  const lower = path.toLowerCase();
  return (
    lower.includes("/tmp/") ||
    lower.includes("/logs/") ||
    lower.includes("manifest") ||
    lower.includes("chunk") ||
    lower.includes("raw-dump") ||
    lower.endsWith(".log") ||
    lower.endsWith(".db") ||
    lower.endsWith(".sqlite")
  );
}

function actionsForView(preferredView: string) {
  return [
    { kind: "open_view", label: "Preview", view: preferredView },
    { kind: "download", label: "Download" },
  ];
}

function allowedStrings(value: unknown, allowed: string[], fallback: string[]): string[] {
  const selected = Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && allowed.includes(item))
    : [];
  return selected.length > 0 ? selected : fallback;
}

function allowedEffects(value: unknown) {
  if (!Array.isArray(value)) return undefined;
  const effects = value.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const effect = item as Record<string, unknown>;
    const kind = optionalString(effect.kind);
    if (!kind || !PRESENTATION_EFFECTS.includes(kind)) return [];
    const panel = optionalString(effect.panel);
    return [{
      kind,
      ...(panel && PRESENTATION_PANELS.includes(panel) ? { panel } : {}),
      ...(optionalString(effect.surface) ? { surface: optionalString(effect.surface) } : {}),
      ...(optionalString(effect.presentationId) ? { presentationId: optionalString(effect.presentationId) } : {}),
      ...(effect.mode === "assertive" || effect.mode === "soft" ? { mode: effect.mode } : {}),
    }];
  });
  return effects.length > 0 ? effects : undefined;
}

function presentationId(runId: string, path: string, index: number): string {
  const suffix = path.replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "file";
  return `presentation_${runId}_${index}_${suffix}`;
}

function fileName(path: string): string {
  return path.split("/").filter(Boolean).pop() ?? path;
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`Missing required input field: ${field}`);
  return value.trim();
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}
