import type { MemoryEntryId, OrgId, UserId } from "./ids.js";

export type AgentMemoryEntry = {
  id: MemoryEntryId;
  orgId: OrgId;
  scope: "thread" | "workspace" | "project" | "user" | "organization" | "skill";
  scopeId?: string;
  key: string;
  value: string;
  owner?: UserId;
  source?: string;
  confidence?: number;
  visibility?: "private" | "shared" | "org";
  retention?: string;
  createdAt: string;
  updatedAt: string;
};
