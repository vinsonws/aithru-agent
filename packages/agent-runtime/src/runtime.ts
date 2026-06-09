import type {
  AgentEngine,
  AgentEngineRunInput,
  AgentEvent,
  AgentResumeInput,
  AgentRunOptions,
  AgentTaskOutput,
} from "@aithru/agent-core";
import { ClassifyEngine } from "./engines/classify.js";
import { PlanRunReviewEngine } from "./engines/plan-run-review.js";
import { DeepResearchEngine } from "./engines/deep-research.js";
import { collectAgentTaskOutput } from "./errors.js";

export type AgentRuntimeOptions = {
  engines?: AgentEngine[];
};

export class AgentRuntime {
  private readonly engines = new Map<string, AgentEngine>();

  constructor(options: AgentRuntimeOptions = {}) {
    for (const engine of options.engines ?? [
      new ClassifyEngine(),
      new PlanRunReviewEngine(),
      new DeepResearchEngine(),
    ]) {
      this.engines.set(engine.name, engine);
    }
  }

  run<TOptions extends AgentRunOptions = AgentRunOptions>(
    engineName: string,
    input: AgentEngineRunInput<TOptions>,
  ): AsyncIterable<AgentEvent> {
    const engine = this.engines.get(engineName);
    if (!engine) {
      throw new Error(`Unknown agent engine: ${engineName}`);
    }

    return engine.run(input);
  }

  async runTask<TOptions extends AgentRunOptions = AgentRunOptions>(
    engineName: string,
    input: AgentEngineRunInput<TOptions>,
  ): Promise<AgentTaskOutput> {
    return collectAgentTaskOutput(this.run(engineName, input));
  }

  resume<TOptions extends AgentRunOptions = AgentRunOptions>(
    engineName: string,
    input: AgentResumeInput<TOptions>,
  ): AsyncIterable<AgentEvent> {
    const engine = this.engines.get(engineName);
    if (!engine) {
      throw new Error(`Unknown agent engine: ${engineName}`);
    }

    if (!engine.resume) {
      throw new Error(
        `Agent engine does not support resume: ${engineName}`,
      );
    }

    return engine.resume(input);
  }

  async resumeTask<TOptions extends AgentRunOptions = AgentRunOptions>(
    engineName: string,
    input: AgentResumeInput<TOptions>,
  ): Promise<AgentTaskOutput> {
    return collectAgentTaskOutput(this.resume(engineName, input));
  }
}
