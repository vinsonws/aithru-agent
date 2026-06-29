export type ToolRiskLevel = "low" | "medium" | "high";

export interface AgentToolDescriptor {
  name: string;
  description: string;
  risk_level: ToolRiskLevel;
  requires_approval: boolean;
  required_scopes: string[];
  input_schema: Record<string, unknown>;
}

export interface AgentToolCallRequest {
  id: string;
  name: string;
  input: Record<string, unknown>;
  run_id: string;
}

export interface AgentToolCallResult {
  id: string;
  name: string;
  output: unknown;
  error?: {
    code: string;
    message: string;
    retryable: boolean;
    details?: unknown;
  };
}

export interface AgentToolApprovalPolicy {
  requires_approval: boolean;
  risk_level: ToolRiskLevel;
  auto_approve_scopes?: string[];
}

export interface AgentSkillConfig {
  name: string;
  allowed_tools: string[];
  denied_tools: string[];
  required_scopes: string[];
}
