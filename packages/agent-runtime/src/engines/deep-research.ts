import type {
  AgentEngine,
  AgentEngineRunInput,
  AgentArtifact,
  AgentEvent,
  AgentPlan,
  AgentResearchOptions,
  AgentResumeInput,
  AgentReviewResult,
  AgentTaskOutput,
  AgentToolRequest,
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
import { resumeEnginePreamble, processToolCallEvent } from "../approval.js";
import {
  createResearchCollection,
  collectResearchOutput,
  normalizeResearchReport,
  researchTimeoutError,
  extractResearchCollection,
  boundedCount,
} from "../research/normalize.js";

export class DeepResearchEngine implements AgentEngine<AgentResearchOptions> {
  readonly name = ENGINE_NAMES.deepResearch;

  async *run(
    input: AgentEngineRunInput<AgentResearchOptions>,
  ): AsyncIterable<AgentEvent> {
    const options = input.options as AgentResearchOptions | undefined;
    const timeoutMs =
      typeof options?.timeoutMs === "number" &&
      Number.isFinite(options.timeoutMs)
        ? Math.max(0, options.timeoutMs)
        : undefined;
    const deadlineAt =
      timeoutMs === undefined ? undefined : Date.now() + timeoutMs;
    const timedOut = () => deadlineAt !== undefined && Date.now() > deadlineAt;

    yield await emitEvent(input, {
      type: "agent.task.created",
      taskId: input.task.id,
      task: input.task,
    });

    if (timeoutMs !== undefined && timedOut()) {
      yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
      return;
    }

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

    if (timeoutMs !== undefined && timedOut()) {
      yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
      return;
    }

    const plan = normalizePlan(
      input.task.id,
      firstStructuredOutput(planResult.events) ??
        firstFinalOutput(planResult.events),
    );
    const planCompleted: AgentEvent = {
      type: "agent.plan.completed",
      taskId: input.task.id,
      plan,
    };
    yield await emitEvent(input, planCompleted);

    const collection = createResearchCollection();
    const maxSteps = boundedCount(options?.maxSteps, plan.steps.length);
    const boundedSteps = plan.steps.slice(0, maxSteps);

    for (
      let stepIndex = 0;
      stepIndex < boundedSteps.length;
      stepIndex += 1
    ) {
      const step = boundedSteps[stepIndex]!;
      if (timeoutMs !== undefined && timedOut()) {
        yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
        return;
      }

      const stepStarted: AgentEvent = {
        type: "agent.step.started",
        taskId: input.task.id,
        stepId: step.id,
        step,
      };
      yield await emitEvent(input, stepStarted);

      const stepResult = await collectModelEvents(input, "execute", step, plan);
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
            artifacts: [],
            stepIndex,
            stepEvents,
            eventIndex,
            engineName: ENGINE_NAMES.deepResearch,
            phase: "deep-research.step",
            extraResumeMetadata: { researchCollection: collection },
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
          collectResearchOutput(collection, result.result.output);
        }
      }

      collectResearchOutput(
        collection,
        firstFinalOutput(stepEvents) ??
          firstStructuredOutput(stepEvents),
      );
    }

    if (timeoutMs !== undefined && timedOut()) {
      yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
      return;
    }

    const synthesisResult = await collectModelEvents(
      input,
      "execute",
      undefined,
      plan,
    );
    if (synthesisResult.error) {
      yield await emitTaskFailed(input, synthesisResult.error);
      return;
    }

    const synthesisEvents = synthesisResult.events;
    for (
      let eventIndex = 0;
      eventIndex < synthesisEvents.length;
      eventIndex += 1
    ) {
      const event = synthesisEvents[eventIndex]!;
      if (event.type === "text.delta") {
        const deltaEvent: AgentEvent = {
          type: "agent.model.delta",
          taskId: input.task.id,
          text: event.text,
        };
        yield await emitEvent(input, deltaEvent);
      }

      if (event.type === "tool_call.proposed") {
        const { stepId: _stepId, ...request } = event.toolCall;
        const result = yield* processToolCallEvent({
          input,
          step: undefined,
          request,
          plan,
          artifacts: [],
          stepIndex: undefined,
          stepEvents: synthesisEvents,
          eventIndex,
          engineName: ENGINE_NAMES.deepResearch,
          phase: "deep-research.synthesis",
          extraResumeMetadata: { researchCollection: collection },
        });
        if (result.kind === "failed") return;
        if (result.kind === "paused") return;
        collectResearchOutput(collection, result.result.output);
      }
    }

    if (timeoutMs !== undefined && timedOut()) {
      yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
      return;
    }

    const report = normalizeResearchReport(
      input.task.goal,
      firstStructuredOutput(synthesisResult.events) ??
        firstFinalOutput(synthesisResult.events),
      collection,
      options,
    );

    let artifact: AgentArtifact;
    try {
      artifact = await createArtifact(input, {
        type: "report",
        name: "deep-research-report",
        content: report,
        mediaType: "application/json",
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

    let review: AgentReviewResult | undefined;
    if (options?.review ?? true) {
      const reviewStarted: AgentEvent = {
        type: "agent.review.started",
        taskId: input.task.id,
      };
      yield await emitEvent(input, reviewStarted);

      const reviewResult = await collectModelEvents(
        input,
        "review",
        undefined,
        plan,
      );
      if (reviewResult.error) {
        yield await emitTaskFailed(input, reviewResult.error);
        return;
      }

      review = normalizeReview(
        firstStructuredOutput(reviewResult.events) ??
          firstFinalOutput(reviewResult.events),
      );
      const reviewCompleted: AgentEvent = {
        type: "agent.review.completed",
        taskId: input.task.id,
        review,
      };
      yield await emitEvent(input, reviewCompleted);
    }

    const artifacts = [artifact];
    const output: AgentTaskOutput = {
      status:
        review?.status === "needs_rerun"
          ? "needs_rerun"
          : review?.status === "failed"
            ? "failed"
            : "completed",
      summary: report.summary,
      plan,
      artifacts,
      ...(review ? { review } : {}),
      metadata: {
        research: report,
      },
    };

    const completedEvent: AgentEvent = {
      type: "agent.task.completed",
      taskId: input.task.id,
      output,
    };
    yield await emitEvent(input, completedEvent);
  }

  async *resume(
    input: AgentResumeInput<AgentResearchOptions>,
  ): AsyncIterable<AgentEvent> {
    const preamble = yield* resumeEnginePreamble(
      input,
      ENGINE_NAMES.deepResearch,
      {
        allowedPhases: ["deep-research.step", "deep-research.synthesis"],
        requiresStepFor: ["deep-research.step"],
        forbidsStepFor: ["deep-research.synthesis"],
      },
    );
    if (!preamble) return;

    const { resumeState, plan, toolResult } = preamble;
    const options = input.options as AgentResearchOptions | undefined;
    const collection = extractResearchCollection(resumeState);
    const currentStep = resumeState.currentStep;

    collectResearchOutput(collection, toolResult.output);

    const phase = resumeState.phase;

    if (phase === "deep-research.step") {
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
            stepId: currentStep!.id,
            text: event.text,
          });
        }

        if (event.type === "tool_call.proposed") {
          const request: AgentToolRequest = {
            ...event.toolCall,
            stepId: currentStep!.id,
          };
          const result = yield* processToolCallEvent({
            input,
            step: currentStep!,
            request,
            plan,
            artifacts: [],
            stepIndex: resumeState.currentStepIndex,
            stepEvents: resumeState.pendingModelEvents,
            eventIndex,
            engineName: ENGINE_NAMES.deepResearch,
            phase: "deep-research.step",
            extraResumeMetadata: { researchCollection: collection },
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
          collectResearchOutput(collection, result.result.output);
        }
      }

      collectResearchOutput(
        collection,
        firstFinalOutput(resumeState.pendingModelEvents) ??
          firstStructuredOutput(resumeState.pendingModelEvents),
      );

      const boundedSteps = plan.steps.slice(
        0,
        boundedCount(options?.maxSteps, plan.steps.length),
      );
      for (
        let remainingIndex = (resumeState.currentStepIndex ?? 0) + 1;
        remainingIndex < boundedSteps.length;
        remainingIndex += 1
      ) {
        const step = boundedSteps[remainingIndex]!;
        yield emitEvent(input, {
          type: "agent.step.started",
          taskId: input.task.id,
          stepId: step.id,
          step,
        });

        const stepResult = await collectModelEvents(
          input,
          "execute",
          step,
          plan,
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
              stepId: step.id,
              text: event.text,
            });
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
              artifacts: [],
              stepIndex: remainingIndex,
              stepEvents: stepResult.events,
              eventIndex,
              engineName: ENGINE_NAMES.deepResearch,
              phase: "deep-research.step",
              extraResumeMetadata: { researchCollection: collection },
            });
            if (result.kind === "failed") return;
            if (result.kind === "paused") return;
            collectResearchOutput(collection, result.result.output);
          }
        }

        collectResearchOutput(
          collection,
          firstFinalOutput(stepResult.events) ??
            firstStructuredOutput(stepResult.events),
        );
      }

      const synthesisResult = await collectModelEvents(
        input,
        "execute",
        undefined,
        plan,
      );
      if (synthesisResult.error) {
        yield await emitTaskFailed(input, synthesisResult.error);
        return;
      }

      for (
        let eventIndex = 0;
        eventIndex < synthesisResult.events.length;
        eventIndex += 1
      ) {
        const event = synthesisResult.events[eventIndex]!;
        if (event.type === "text.delta") {
          yield emitEvent(input, {
            type: "agent.model.delta",
            taskId: input.task.id,
            text: event.text,
          });
        }

        if (event.type === "tool_call.proposed") {
          const { stepId: _stepId, ...request } = event.toolCall;
          const result = yield* processToolCallEvent({
            input,
            step: undefined,
            request,
            plan,
            artifacts: [],
            stepIndex: undefined,
            stepEvents: synthesisResult.events,
            eventIndex,
            engineName: ENGINE_NAMES.deepResearch,
            phase: "deep-research.synthesis",
            extraResumeMetadata: { researchCollection: collection },
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
          collectResearchOutput(collection, result.result.output);
        }
      }

      collectResearchOutput(
        collection,
        firstStructuredOutput(synthesisResult.events) ??
          firstFinalOutput(synthesisResult.events),
      );

      const report = normalizeResearchReport(
        input.task.goal,
        firstStructuredOutput(synthesisResult.events) ??
          firstFinalOutput(synthesisResult.events),
        collection,
        options,
      );

      let artifact: AgentArtifact;
      try {
        artifact = await createArtifact(input, {
          type: "report",
          name: "deep-research-report",
          content: report,
          mediaType: "application/json",
        });
      } catch (error) {
        yield await emitTaskFailed(
          input,
          toAgentError(error, "artifact_exception"),
        );
        return;
      }

      yield emitEvent(input, {
        type: "agent.artifact.created",
        taskId: input.task.id,
        artifact,
      });

      let review: AgentReviewResult | undefined;
      if (options?.review ?? true) {
        yield emitEvent(input, {
          type: "agent.review.started",
          taskId: input.task.id,
        });

        const reviewResult = await collectModelEvents(
          input,
          "review",
          undefined,
          plan,
        );
        if (reviewResult.error) {
          yield await emitTaskFailed(input, reviewResult.error);
          return;
        }

        review = normalizeReview(
          firstStructuredOutput(reviewResult.events) ??
            firstFinalOutput(reviewResult.events),
        );
        yield emitEvent(input, {
          type: "agent.review.completed",
          taskId: input.task.id,
          review,
        });
      }

      const artifacts: AgentArtifact[] = [artifact];
      yield emitEvent(input, {
        type: "agent.task.completed",
        taskId: input.task.id,
        output: {
          status:
            review?.status === "needs_rerun"
              ? "needs_rerun"
              : review?.status === "failed"
                ? "failed"
                : "completed",
          summary: report.summary,
          plan,
          artifacts,
          ...(review ? { review } : {}),
          metadata: {
            research: report,
          },
        },
      });
    } else {
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
            text: event.text,
          });
        }

        if (event.type === "tool_call.proposed") {
          const { stepId: _stepId, ...request } = event.toolCall;
          const result = yield* processToolCallEvent({
            input,
            step: undefined,
            request,
            plan,
            artifacts: [],
            stepIndex: undefined,
            stepEvents: resumeState.pendingModelEvents,
            eventIndex,
            engineName: ENGINE_NAMES.deepResearch,
            phase: "deep-research.synthesis",
            extraResumeMetadata: { researchCollection: collection },
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
          collectResearchOutput(collection, result.result.output);
        }
      }

      collectResearchOutput(
        collection,
        firstStructuredOutput(resumeState.pendingModelEvents) ??
          firstFinalOutput(resumeState.pendingModelEvents),
      );

      const report = normalizeResearchReport(
        input.task.goal,
        firstStructuredOutput(resumeState.pendingModelEvents) ??
          firstFinalOutput(resumeState.pendingModelEvents),
        collection,
        options,
      );

      let artifact: AgentArtifact;
      try {
        artifact = await createArtifact(input, {
          type: "report",
          name: "deep-research-report",
          content: report,
          mediaType: "application/json",
        });
      } catch (error) {
        yield await emitTaskFailed(
          input,
          toAgentError(error, "artifact_exception"),
        );
        return;
      }

      yield emitEvent(input, {
        type: "agent.artifact.created",
        taskId: input.task.id,
        artifact,
      });

      let review: AgentReviewResult | undefined;
      if (options?.review ?? true) {
        yield emitEvent(input, {
          type: "agent.review.started",
          taskId: input.task.id,
        });

        const reviewResult = await collectModelEvents(
          input,
          "review",
          undefined,
          plan,
        );
        if (reviewResult.error) {
          yield await emitTaskFailed(input, reviewResult.error);
          return;
        }

        review = normalizeReview(
          firstStructuredOutput(reviewResult.events) ??
            firstFinalOutput(reviewResult.events),
        );
        yield emitEvent(input, {
          type: "agent.review.completed",
          taskId: input.task.id,
          review,
        });
      }

      const artifacts: AgentArtifact[] = [artifact];
      yield emitEvent(input, {
        type: "agent.task.completed",
        taskId: input.task.id,
        output: {
          status:
            review?.status === "needs_rerun"
              ? "needs_rerun"
              : review?.status === "failed"
                ? "failed"
                : "completed",
          summary: report.summary,
          plan,
          artifacts,
          ...(review ? { review } : {}),
          metadata: {
            research: report,
          },
        },
      });
    }
  }
}
