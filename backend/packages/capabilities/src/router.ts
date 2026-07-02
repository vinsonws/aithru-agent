import type { AgentToolDescriptor, AgentToolCallRequest, AgentToolCallResult } from "./descriptors.js";
import type { RunContextInput } from "./policy.js";

export interface ToolPrepareResult {
  allowed: boolean;
  requires_approval: boolean;
  reason?: string;
  audit_event_type?: string;
}

export interface CapabilityRouter {
  listTools(ctx: RunContextInput): Promise<AgentToolDescriptor[]>;
  prepareToolCall(req: AgentToolCallRequest, ctx: RunContextInput): Promise<ToolPrepareResult>;
  executeToolCall(req: AgentToolCallRequest, ctx: RunContextInput): Promise<AgentToolCallResult>;
}
