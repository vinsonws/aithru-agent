import type { AgentToolDescriptor, AgentToolCallRequest, AgentToolCallResult } from "./descriptors.js";

export interface ToolPrepareResult {
  allowed: boolean;
  requires_approval: boolean;
  reason?: string;
}

export interface CapabilityRouter {
  listTools(runId: string): Promise<AgentToolDescriptor[]>;
  prepareToolCall(
    req: AgentToolCallRequest,
  ): Promise<ToolPrepareResult>;
  executeToolCall(
    req: AgentToolCallRequest,
  ): Promise<AgentToolCallResult>;
}
