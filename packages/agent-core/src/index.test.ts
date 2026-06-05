import { describe, expect, test } from "vitest";
import type { AgentEvent } from "./index.js";
import { agentTraceEventFromAgentEvent } from "./index.js";

describe("agentTraceEventFromAgentEvent", () => {
  test("maps agent.task.created into a task created trace event", () => {
    const event: AgentEvent = {
      type: "agent.task.created",
      taskId: "task_trace",
      task: {
        id: "task_trace",
        goal: "Trace this task.",
      },
    };

    expect(agentTraceEventFromAgentEvent(event)).toEqual({
      kind: "agent.task",
      phase: "created",
      agentEventType: "agent.task.created",
      taskId: "task_trace",
      summary: "Trace this task.",
      payload: event,
    });
  });

  test("maps agent.tool.proposed with toolName and stepId", () => {
    const event: AgentEvent = {
      type: "agent.tool.proposed",
      taskId: "task_trace",
      stepId: "step_read",
      request: {
        id: "tool_read",
        toolName: "repo.read",
        arguments: { path: "README.md" },
      },
    };

    expect(agentTraceEventFromAgentEvent(event)).toEqual({
      kind: "agent.tool",
      phase: "proposed",
      agentEventType: "agent.tool.proposed",
      taskId: "task_trace",
      stepId: "step_read",
      toolName: "repo.read",
      payload: event,
    });
  });

  test("maps agent.task.failed with errorCode", () => {
    const event: AgentEvent = {
      type: "agent.task.failed",
      taskId: "task_trace",
      error: {
        code: "provider_error",
        message: "Provider failed.",
      },
    };

    expect(agentTraceEventFromAgentEvent(event)).toEqual({
      kind: "agent.error",
      phase: "failed",
      agentEventType: "agent.task.failed",
      taskId: "task_trace",
      errorCode: "provider_error",
      summary: "Provider failed.",
      payload: event,
    });
  });

  test("preserves the original event as payload", () => {
    const event: AgentEvent = {
      type: "agent.model.delta",
      taskId: "task_trace",
      stepId: "step_write",
      text: "hello",
    };

    expect(agentTraceEventFromAgentEvent(event).payload).toBe(event);
  });
});
