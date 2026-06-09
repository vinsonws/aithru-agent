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

  test("maps agent.tool.approval_requested with toolName and stepId", () => {
    const event: AgentEvent = {
      type: "agent.tool.approval_requested",
      taskId: "task_trace",
      stepId: "step_del",
      approval: {
        id: "approval_1",
        taskId: "task_trace",
        stepId: "step_del",
        toolRequest: {
          id: "tool_del",
          toolName: "repo.delete",
          arguments: { path: "x" },
        },
        riskLevel: "dangerous",
      },
    };

    expect(agentTraceEventFromAgentEvent(event)).toEqual({
      kind: "agent.approval",
      phase: "requested",
      agentEventType: "agent.tool.approval_requested",
      taskId: "task_trace",
      stepId: "step_del",
      toolName: "repo.delete",
      summary: "Approval requested for repo.delete.",
      payload: event,
    });
  });

  test("maps agent.task.paused with summary", () => {
    const event: AgentEvent = {
      type: "agent.task.paused",
      taskId: "task_trace",
      approval: {
        id: "approval_1",
        taskId: "task_trace",
        toolRequest: {
          id: "tool_del",
          toolName: "repo.delete",
          arguments: { path: "x" },
        },
        riskLevel: "dangerous",
      },
      output: {
        status: "paused",
        summary: "Approval required for tool \"repo.delete\".",
        artifacts: [],
      },
    };

    expect(agentTraceEventFromAgentEvent(event)).toEqual({
      kind: "agent.task",
      phase: "paused",
      agentEventType: "agent.task.paused",
      taskId: "task_trace",
      summary: "Approval required for tool \"repo.delete\".",
      payload: event,
    });
  });

  test("maps agent.tool.approval_resolved with toolName", () => {
    const event: AgentEvent = {
      type: "agent.tool.approval_resolved",
      taskId: "task_trace",
      stepId: "step_del",
      approval: {
        id: "approval_1",
        taskId: "task_trace",
        stepId: "step_del",
        toolRequest: {
          id: "tool_del",
          toolName: "repo.delete",
          arguments: { path: "x" },
        },
        riskLevel: "dangerous",
      },
      response: {
        approvalId: "approval_1",
        decision: "approved",
        reason: "Looks safe.",
      },
    };

    expect(agentTraceEventFromAgentEvent(event)).toEqual({
      kind: "agent.approval",
      phase: "resolved",
      agentEventType: "agent.tool.approval_resolved",
      taskId: "task_trace",
      stepId: "step_del",
      toolName: "repo.delete",
      summary: "Looks safe.",
      payload: event,
    });
  });

  test("maps agent.task.resumed with taskId", () => {
    const event: AgentEvent = {
      type: "agent.task.resumed",
      taskId: "task_trace",
      approval: {
        id: "approval_1",
        taskId: "task_trace",
        toolRequest: {
          id: "tool_del",
          toolName: "repo.delete",
          arguments: { path: "x" },
        },
        riskLevel: "dangerous",
      },
      response: {
        approvalId: "approval_1",
        decision: "approved",
      },
      resumeState: {
        id: "resume_1",
        engineName: "plan-run-review",
        taskId: "task_trace",
        phase: "plan-run-review.step",
        approval: {
          id: "approval_1",
          taskId: "task_trace",
          toolRequest: {
            id: "tool_del",
            toolName: "repo.delete",
            arguments: { path: "x" },
          },
          riskLevel: "dangerous",
        },
        artifacts: [],
        pendingModelEvents: [],
      },
    };

    expect(agentTraceEventFromAgentEvent(event)).toEqual({
      kind: "agent.task",
      phase: "resumed",
      agentEventType: "agent.task.resumed",
      taskId: "task_trace",
      summary: "Task resumed for approval approval_1.",
      payload: event,
    });
  });
});
