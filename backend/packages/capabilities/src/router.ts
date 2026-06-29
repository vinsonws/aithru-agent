import type { AgentToolDescriptor, AgentToolCallRequest, AgentToolCallResult } from "./descriptors.js";
import type { RunContext } from "./policy.js";

export interface ToolPrepareResult {
  allowed: boolean;
  requires_approval: boolean;
  reason?: string;
  audit_event_type?: string;
}

export interface CapabilityRouter {
  listTools(ctx: RunContext): Promise<AgentToolDescriptor[]>;
  prepareToolCall(req: AgentToolCallRequest, ctx: RunContext): Promise<ToolPrepareResult>;
  executeToolCall(req: AgentToolCallRequest, ctx: RunContext): Promise<AgentToolCallResult>;
}
