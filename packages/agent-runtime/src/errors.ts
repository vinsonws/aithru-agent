import type { AgentError, AgentEvent, AgentTaskOutput } from "@aithru/agent-core";

export class AgentTaskFailedError extends Error {
  readonly agentError: AgentError;

  constructor(agentError: AgentError) {
    super(`Agent task failed: ${agentError.message}`);
    this.name = "AgentTaskFailedError";
    this.agentError = agentError;
  }
}

export async function collectAgentTaskOutput(
  events: AsyncIterable<AgentEvent>,
): Promise<AgentTaskOutput> {
  let output: AgentTaskOutput | undefined;

  for await (const event of events) {
    if (event.type === "agent.task.failed") {
      throw new AgentTaskFailedError(event.error);
    }

    if (event.type === "agent.task.paused") {
      return event.output;
    }

    if (event.type === "agent.task.completed") {
      output = event.output;
    }
  }

  if (!output) {
    throw new Error("Agent run completed without agent.task.completed event.");
  }

  return output;
}
