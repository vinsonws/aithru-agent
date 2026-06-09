import type {
  AgentEngine,
  AgentEngineRunInput,
  AgentEvent,
  AgentTaskOutput,
} from "@aithru/agent-core";
import {
  collectModelEvents,
  emitEvent,
  emitTaskFailed,
  firstFinalOutput,
  firstStructuredOutput,
  createArtifact,
  normalizeClassification,
  toAgentError,
} from "../utils.js";

export class ClassifyEngine implements AgentEngine {
  readonly name = "classify";

  async *run(input: AgentEngineRunInput): AsyncIterable<AgentEvent> {
    yield await emitEvent(input, {
      type: "agent.task.created",
      taskId: input.task.id,
      task: input.task,
    });

    const modelResult = await collectModelEvents(input, "classify");
    if (modelResult.error) {
      yield await emitTaskFailed(input, modelResult.error);
      return;
    }

    const events = modelResult.events;
    for (const event of events) {
      if (event.type === "text.delta") {
        const agentEvent: AgentEvent = {
          type: "agent.model.delta",
          taskId: input.task.id,
          text: event.text,
        };
        yield await emitEvent(input, agentEvent);
      }
    }

    const classification = normalizeClassification(
      firstStructuredOutput(events) ?? firstFinalOutput(events),
    );
    let artifact;
    try {
      artifact = await createArtifact(input, {
        type: "decision",
        name: "classification",
        content: classification,
      });
    } catch (error) {
      yield await emitTaskFailed(
        input,
        toAgentError(error, "artifact_exception"),
      );
      return;
    }

    const artifactEvent: AgentEvent = {
      type: "agent.artifact.created",
      taskId: input.task.id,
      artifact,
    };
    yield await emitEvent(input, artifactEvent);

    const output: AgentTaskOutput = {
      status: "completed",
      summary: classification.reason ?? `Route: ${classification.route}`,
      artifacts: [artifact],
      metadata: { classification },
    };

    const completedEvent: AgentEvent = {
      type: "agent.task.completed",
      taskId: input.task.id,
      output,
    };
    yield await emitEvent(input, completedEvent);
  }
}
