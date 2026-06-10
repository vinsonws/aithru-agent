import type { TodoId, RunId } from "./ids.js";

export type AgentTodoStatus = "pending" | "running" | "done" | "blocked" | "cancelled";

export type AgentTodoCreatorType = "agent" | "user" | "system";

export type AgentTodo = {
  id: TodoId;
  runId: RunId;
  title: string;
  description?: string;
  status: AgentTodoStatus;
  createdBy: AgentTodoCreatorType;
  order: number;
};
