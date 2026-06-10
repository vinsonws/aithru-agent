declare const AGENT_ID_BRAND: unique symbol;

export type Brand<T, B extends string> = T & { [K in B]: true };

export type ThreadId = Brand<string, "ThreadId">;
export type MessageId = Brand<string, "MessageId">;
export type SkillId = Brand<string, "SkillId">;
export type RunId = Brand<string, "RunId">;
export type TodoId = Brand<string, "TodoId">;
export type WorkspaceId = Brand<string, "WorkspaceId">;
export type ArtifactId = Brand<string, "ArtifactId">;
export type ToolCallId = Brand<string, "ToolCallId">;
export type ApprovalId = Brand<string, "ApprovalId">;
export type SubagentRunId = Brand<string, "SubagentRunId">;
export type MemoryEntryId = Brand<string, "MemoryEntryId">;
export type EventId = Brand<string, "EventId">;
export type OrgId = Brand<string, "OrgId">;
export type UserId = Brand<string, "UserId">;
