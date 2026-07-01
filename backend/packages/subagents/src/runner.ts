import type { AgentStore } from "@aithru-agent/persistence";
import type { AgentEventWriter } from "@aithru-agent/stream";
import type { CapabilityRouter } from "@aithru-agent/capabilities";
import { WorkerRunner } from "@aithru-agent/worker";
import type { AgentRun } from "@aithru-agent/contracts";
import { ModelTurnLoop, type ToolCallStep } from "@aithru-agent/harness";
import type { AgentModelAdapter } from "@aithru-agent/model";
import type { SkillResolver } from "@aithru-agent/skills";

export interface SubagentSpec {
  task: string;
  scopes: string[];
}

export interface SubagentResult {
  run_id: string;
  status: string;
  content: string | null;
  error?: { code: string; message: string };
}

export interface SubagentRunnerOptions {
  modelAdapterFactory?: (run: AgentRun) => AgentModelAdapter;
  skillResolver?: SkillResolver;
  childLimits?: {
    maxModelRequests: number;
    maxToolExecutions: number;
  };
}

export class SubagentRunner {
  constructor(
    private store: AgentStore,
    private eventWriter: AgentEventWriter,
    private capabilityRouter: CapabilityRouter,
    private options: SubagentRunnerOptions = {},
  ) {}

  async delegate(
    parentRun: AgentRun,
    spec: SubagentSpec,
    script?: { steps: ToolCallStep[]; finalContent?: string },
  ): Promise<SubagentResult> {
    const childRun: AgentRun = {
      id: `run_sub_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
      org_id: parentRun.org_id,
      actor_user_id: parentRun.actor_user_id,
      source: "delegated_task",
      thread_id: parentRun.thread_id,
      workspace_id: parentRun.workspace_id,
      task_msg: spec.task,
      scopes: spec.scopes,
      harness_options: {
        ...(isRecord(parentRun.harness_options) ? parentRun.harness_options : {}),
        delegated_from_run_id: parentRun.id,
        max_model_requests: this.options.childLimits?.maxModelRequests ?? 15,
        max_tool_executions: this.options.childLimits?.maxToolExecutions ?? 30,
      } as AgentRun["harness_options"],
      status: "queued",
      started_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      completed_at: null,
      current_approval_id: null,
      claim: null,
      result: null,
      error: null,
    };
    this.store.createRun(childRun);

    // Wait for completion (simplified: run synchronously in P2)
    if (script) {
      const worker = new WorkerRunner({
        store: this.store,
        eventWriter: this.eventWriter,
        capabilityRouter: this.capabilityRouter,
      });
      const completed = await worker.startRun(childRun, script);
      return {
        run_id: completed.id,
        status: String(completed.status),
        content: completed.result?.content || null,
        error: completed.error as any,
      };
    }

    if (!this.options.modelAdapterFactory) {
      return { run_id: childRun.id, status: "queued", content: null };
    }

    const completed = await new ModelTurnLoop({
      store: this.store,
      eventWriter: this.eventWriter,
      capabilityRouter: this.capabilityRouter,
      modelAdapter: this.options.modelAdapterFactory(childRun),
      skillResolver: this.options.skillResolver,
    }).execute(childRun);

    return {
      run_id: completed.id,
      status: String(completed.status),
      content: contentFromRun(completed),
      error: completed.error as any,
    };
  }
}

function contentFromRun(run: AgentRun): string | null {
  const result = run.result;
  if (!result || typeof result !== "object") return null;
  const content = (result as Record<string, unknown>).content;
  return typeof content === "string" ? content : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}
