import type {
  AgentEngine,
  AgentEngineRunInput,
  AgentError,
  AgentEvent,
  AgentArtifact,
  AgentPlan,
  AgentPlanStep,
  AgentResumeInput,
  AgentReviewResult,
  AgentTaskOutput,
  AgentToolRequest,
  AgentToolResult,
} from "@aithru/agent-core";
import {
  collectModelEvents,
  createArtifact,
  emitEvent,
  emitTaskFailed,
  firstFinalOutput,
  firstStructuredOutput,
  normalizePlan,
  normalizeReview,
  toAgentError,
} from "../utils.js";
import { ENGINE_NAMES } from "../constants.js";
import {
  resumeEnginePreamble,
  processToolCallEvent,
} from "../approval.js";

export class PlanRunReviewEngine implements AgentEngine {
  readonly name = ENGINE_NAMES.planRunReview;

  async *run(input: AgentEngineRunInput): AsyncIterable<AgentEvent> {
    yield await emitEvent(input, {
      type: "agent.task.created",
      taskId: input.task.id,
      task: input.task,
    });

    const planStarted: AgentEvent = {
      type: "agent.plan.started",
      taskId: input.task.id,
    };
    yield await emitEvent(input, planStarted);

    const planResult = await collectModelEvents(input, "plan");
    if (planResult.error) {
      yield await emitTaskFailed(input, planResult.error);
      return;
    }

    const planEvents = planResult.events;
    const plan = normalizePlan(
      input.task.id,
      firstStructuredOutput(planEvents) ?? firstFinalOutput(planEvents),
    );

    const planCompleted: AgentEvent = {
      type: "agent.plan.completed",
      taskId: input.task.id,
      plan,
    };
    yield await emitEvent(input, planCompleted);

    const artifacts: AgentArtifact[] = [];
    const boundedSteps = plan.steps.slice(
      0,
      input.options?.maxSteps ?? plan.steps.length,
    );

    for (let stepIndex = 0; stepIndex < boundedSteps.length; stepIndex += 1) {
      const step = boundedSteps[stepIndex]!;
      const stepStarted: AgentEvent = {
        type: "agent.step.started",
        taskId: input.task.id,
        stepId: step.id,
        step,
      };
      yield await emitEvent(input, stepStarted);

      const stepResult = await collectModelEvents(input, "execute", step);
      if (stepResult.error) {
        yield await emitTaskFailed(input, stepResult.error);
        return;
      }

      const stepEvents = stepResult.events;
      for (
        let eventIndex = 0;
        eventIndex < stepEvents.length;
        eventIndex += 1
      ) {
        const event = stepEvents[eventIndex]!;
        if (event.type === "text.delta") {
          const deltaEvent: AgentEvent = {
            type: "agent.model.delta",
            taskId: input.task.id,
            stepId: step.id,
            text: event.text,
          };
          yield await emitEvent(input, deltaEvent);
        }

        if (event.type === "tool_call.proposed") {
          const request: AgentToolRequest = {
            ...event.toolCall,
            stepId: step.id,
          };
          const result = yield* processToolCallEvent({
            input,
            step,
            request,
            plan,
            artifacts,
            stepIndex,
            stepEvents,
            eventIndex,
            engineName: ENGINE_NAMES.planRunReview,
            phase: "plan-run-review.step",
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
        }
      }

      const stepOutput =
        firstFinalOutput(stepEvents) ?? firstStructuredOutput(stepEvents);
      if (stepOutput !== undefined) {
        let artifact: AgentArtifact;
        try {
          artifact = await createArtifact(input, {
            type: "json",
            name: `${step.id}-output`,
            content: stepOutput,
            sourceStepId: step.id,
          });
        } catch (error) {
          yield await emitTaskFailed(
            input,
            toAgentError(error, "artifact_exception"),
          );
          return;
        }

        artifacts.push(artifact);
        const artifactEvent: AgentEvent = {
          type: "agent.artifact.created",
          taskId: input.task.id,
          artifact,
        };
        yield await emitEvent(input, artifactEvent);
      }
    }

    let review: AgentReviewResult | undefined;
    if (input.options?.review ?? true) {
      const reviewStarted: AgentEvent = {
        type: "agent.review.started",
        taskId: input.task.id,
      };
      yield await emitEvent(input, reviewStarted);

      const reviewResult = await collectModelEvents(input, "review");
      if (reviewResult.error) {
        yield await emitTaskFailed(input, reviewResult.error);
        return;
      }

      const reviewEvents = reviewResult.events;
      review = normalizeReview(
        firstStructuredOutput(reviewEvents) ?? firstFinalOutput(reviewEvents),
      );
      const reviewCompleted: AgentEvent = {
        type: "agent.review.completed",
        taskId: input.task.id,
        review,
      };
      yield await emitEvent(input, reviewCompleted);
    }

    const output: AgentTaskOutput = {
      status:
        review?.status === "needs_rerun"
          ? "needs_rerun"
          : review?.status === "failed"
            ? "failed"
            : "completed",
      summary: review?.summary ?? "Agent task completed.",
      plan,
      artifacts,
      ...(review ? { review } : {}),
    };

    const completedEvent: AgentEvent = {
      type: "agent.task.completed",
      taskId: input.task.id,
      output,
    };
    yield await emitEvent(input, completedEvent);
  }

  async *resume(
    input: AgentResumeInput,
  ): AsyncIterable<AgentEvent> {
    const preamble = yield* resumeEnginePreamble(
      input,
      ENGINE_NAMES.planRunReview,
      {
        allowedPhases: ["plan-run-review.step"],
        requiresStepFor: ["plan-run-review.step"],
      },
    );
    if (!preamble) return;

    const { resumeState, step, plan, toolResult } = preamble;

    const stepDefined = step!;
    const stepIndex = resumeState.currentStepIndex!;

    const artifacts: AgentArtifact[] = [...resumeState.artifacts];
    const boundedSteps = plan.steps.slice(
      0,
      input.options?.maxSteps ?? plan.steps.length,
    );

    for (
      let eventIndex = 0;
      eventIndex < resumeState.pendingModelEvents.length;
      eventIndex += 1
    ) {
      const event = resumeState.pendingModelEvents[eventIndex]!;
      if (event.type === "text.delta") {
        yield emitEvent(input, {
          type: "agent.model.delta",
          taskId: input.task.id,
          stepId: stepDefined.id,
          text: event.text,
        });
      }

      if (event.type === "tool_call.proposed") {
        const request: AgentToolRequest = {
          ...event.toolCall,
          stepId: stepDefined.id,
        };
        const result = yield* processToolCallEvent({
          input,
          step: stepDefined,
          request,
          plan,
          artifacts,
          stepIndex,
          stepEvents: resumeState.pendingModelEvents,
          eventIndex,
          engineName: ENGINE_NAMES.planRunReview,
          phase: "plan-run-review.step",
        });
        if (result.kind === "failed") return;
        if (result.kind === "paused") return;
      }
    }

    const pendingOutput =
      firstFinalOutput(resumeState.pendingModelEvents) ??
      firstStructuredOutput(resumeState.pendingModelEvents);
    if (pendingOutput !== undefined) {
      try {
        const artifact = await createArtifact(input, {
          type: "json",
          name: `${stepDefined.id}-output`,
          content: pendingOutput,
          sourceStepId: stepDefined.id,
        });
        artifacts.push(artifact);
        yield emitEvent(input, {
          type: "agent.artifact.created",
          taskId: input.task.id,
          artifact,
        });
      } catch (error) {
        yield await emitTaskFailed(
          input,
          toAgentError(error, "artifact_exception"),
        );
        return;
      }
    }

    for (
      let remainingIndex = stepIndex + 1;
      remainingIndex < boundedSteps.length;
      remainingIndex += 1
    ) {
      const currentStep = boundedSteps[remainingIndex]!;
      yield emitEvent(input, {
        type: "agent.step.started",
        taskId: input.task.id,
        stepId: currentStep.id,
        step: currentStep,
      });

      const stepResult = await collectModelEvents(
        input,
        "execute",
        currentStep,
      );
      if (stepResult.error) {
        yield await emitTaskFailed(input, stepResult.error);
        return;
      }

      for (
        let eventIndex = 0;
        eventIndex < stepResult.events.length;
        eventIndex += 1
      ) {
        const event = stepResult.events[eventIndex]!;
        if (event.type === "text.delta") {
          yield emitEvent(input, {
            type: "agent.model.delta",
            taskId: input.task.id,
            stepId: currentStep.id,
            text: event.text,
          });
        }

        if (event.type === "tool_call.proposed") {
          const request: AgentToolRequest = {
            ...event.toolCall,
            stepId: currentStep.id,
          };
          const result = yield* processToolCallEvent({
            input,
            step: currentStep,
            request,
            plan,
            artifacts,
            stepIndex: remainingIndex,
            stepEvents: stepResult.events,
            eventIndex,
            engineName: ENGINE_NAMES.planRunReview,
            phase: "plan-run-review.step",
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
        }
      }

      const stepOutput =
        firstFinalOutput(stepResult.events) ??
        firstStructuredOutput(stepResult.events);
      if (stepOutput !== undefined) {
        try {
          const artifact = await createArtifact(input, {
            type: "json",
            name: `${currentStep.id}-output`,
            content: stepOutput,
            sourceStepId: currentStep.id,
          });
          artifacts.push(artifact);
          yield emitEvent(input, {
            type: "agent.artifact.created",
            taskId: input.task.id,
            artifact,
          });
        } catch (error) {
          yield await emitTaskFailed(
            input,
            toAgentError(error, "artifact_exception"),
          );
          return;
        }
      }
    }

    let review: AgentReviewResult | undefined;
    if (input.options?.review ?? true) {
      yield emitEvent(input, {
        type: "agent.review.started",
        taskId: input.task.id,
      });

      const reviewResult = await collectModelEvents(input, "review");
      if (reviewResult.error) {
        yield await emitTaskFailed(input, reviewResult.error);
        return;
      }

      const reviewEvents = reviewResult.events;
      review = normalizeReview(
        firstStructuredOutput(reviewEvents) ??
          firstFinalOutput(reviewEvents),
      );
      yield emitEvent(input, {
        type: "agent.review.completed",
        taskId: input.task.id,
        review,
      });
    }

    const output: AgentTaskOutput = {
      status:
        review?.status === "needs_rerun"
          ? "needs_rerun"
          : review?.status === "failed"
            ? "failed"
            : "completed",
      summary: review?.summary ?? "Agent task completed.",
      plan,
      artifacts,
      ...(review ? { review } : {}),
    };

    yield emitEvent(input, {
      type: "agent.task.completed",
      taskId: input.task.id,
      output,
    });
  }
}
