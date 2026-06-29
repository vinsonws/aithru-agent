export interface AgentToolDescriptor {
  name: string;
  description: string;
  risk_level: "low" | "medium" | "high";
  requires_approval: boolean;
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
