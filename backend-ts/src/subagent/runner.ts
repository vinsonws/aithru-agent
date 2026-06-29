// backend-ts/src/subagent/runner.ts

import type { AgentStore } from "../persistence/protocols.js";
import type { AgentEventWriter } from "../stream/writer.js";
import type { CapabilityRouter } from "../capabilities/router.js";
import { WorkerRunner } from "../worker/runner.js";
import type { AgentRun } from "../contracts/types.js";
import type { ToolCallStep } from "../core/run-loop.js";

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

export class SubagentRunner {
  constructor(
    private store: AgentStore,
    private eventWriter: AgentEventWriter,
    private capabilityRouter: CapabilityRouter,
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
      skill_id: null,
      workspace_id: `ws_sub_${Date.now().toString(36)}`,
      task_msg: spec.task,
      scopes: spec.scopes,
      harness_options: null,
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

    return { run_id: childRun.id, status: "queued", content: null };
  }
}
