import type {
  RunId, ApprovalId, OrgId, UserId, SkillId, ThreadId,
} from "@aithru/agent-core";
import type { AgentStreamEvent, AgentEventBus } from "@aithru/agent-stream";
import type { AgentHarnessEnginePorts } from "@aithru/agent-harness";
import { NativeHarnessEngine, ScriptedModelPort } from "@aithru/agent-harness";
import type { AgentServerStore } from "../store/types.js";
import { projectEventIntoStore } from "./project-event.js";

/**
 * Manages concurrent Agent runs.
 *
 * Each run gets its own NativeHarnessEngine instance so that
 * pending approvals, model ports, and run state stay isolated.
 */
export class AgentRunController {
  private engines = new Map<RunId, NativeHarnessEngine>();
  private running = new Set<RunId>();

  constructor(
    private ports: Omit<AgentHarnessEnginePorts, "model">,
    private store: AgentServerStore,
    private eventBus: AgentEventBus,
  ) {}

  /**
   * Start a new agent run.
   *
   * The runId is taken from the first event emitted by the harness (run.created).
   * The async iterable is consumed in the background.
   */
  async startRun(input: {
    orgId: OrgId;
    actorUserId: UserId;
    goal: string;
    threadId?: ThreadId;
    skillId?: SkillId;
    scopes?: string[];
  }): Promise<RunId> {
    const model = new ScriptedModelPort();
    const engine = new NativeHarnessEngine({
      ...this.ports,
      model,
    });

    const rawIterator = engine.run({
      orgId: input.orgId,
      actorUserId: input.actorUserId,
      goal: input.goal,
      threadId: input.threadId,
      skillId: input.skillId,
      scopes: input.scopes,
    });
    const iterator = rawIterator[Symbol.asyncIterator]();

    const first = await iterator.next();
    if (first.done || !first.value) {
      throw new Error("Harness did not produce any events");
    }

    const runId = first.value.runId;
    this.engines.set(runId, engine);
    this.running.add(runId);

    // Project the first event and consume the rest in background
    projectEventIntoStore(first.value, this.store);
    this.consumeRunInBackground(runId, iterator);

    return runId;
  }

  /**
   * Resume a run that is paused for approval.
   */
  async resumeRun(
    runId: RunId,
    approval: {
      approvalId: ApprovalId;
      decision: "approved" | "rejected";
      comment?: string;
    },
  ): Promise<void> {
    const engine = this.engines.get(runId);
    if (!engine) {
      throw new Error(`Run ${runId} is not resumable (no engine found)`);
    }

    if (!this.running.has(runId)) {
      this.running.add(runId);
    }

    const iterator = engine.resume({ runId, approval })[Symbol.asyncIterator]();
    this.consumeRunInBackground(runId, iterator);
  }

  /**
   * Cancel a run.
   */
  async cancelRun(runId: RunId): Promise<void> {
    const engine = this.engines.get(runId);
    if (!engine) {
      throw new Error(`Run ${runId} not found`);
    }
    await engine.cancel(runId);
  }

  /**
   * Check whether a run exists (is managed by this controller).
   */
  hasRun(runId: RunId): boolean {
    return this.engines.has(runId);
  }

  /**
   * Consume an async iterator in the background, projecting events into the store.
   *
   * The engine is kept in the map when the run pauses for approval
   * (iterator returns done without a terminal event). It is cleaned up
   * only when a terminal event (or error) is observed.
   */
  private async consumeRunInBackground(
    runId: RunId,
    iterator: AsyncIterator<AgentStreamEvent>,
  ): Promise<void> {
    let terminal = false;
    try {
      while (true) {
        const result = await iterator.next();
        if (result.done) break;

        projectEventIntoStore(result.value, this.store);

        // Terminal events — signal cleanup
        if (
          result.value.type === "run.completed" ||
          result.value.type === "run.failed" ||
          result.value.type === "run.cancelled"
        ) {
          terminal = true;
          break;
        }
      }
    } catch (err) {
      console.error(`[agent-server] Error consuming events for run ${runId}:`, err);
      terminal = true;
    }

    if (terminal) {
      this.engines.delete(runId);
      this.running.delete(runId);
    }
    // If the generator completed without a terminal event (e.g. paused),
    // the engine stays in the map for a future resume call.
  }
}
