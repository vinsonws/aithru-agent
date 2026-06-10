import type { MessageId, ThreadId, RunId, ArtifactId } from "./ids.js";

export type AgentMessageRole = "user" | "assistant" | "system" | "tool";

export type AgentMessage = {
  id: MessageId;
  threadId: ThreadId;
  role: AgentMessageRole;
  content: string;
  runId?: RunId;
  artifactIds?: ArtifactId[];
  createdAt: string;
};
