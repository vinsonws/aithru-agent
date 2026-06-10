export type AgentErrorCode =
  | "NOT_FOUND"
  | "INVALID_INPUT"
  | "VALIDATION_ERROR"
  | "SKILL_NOT_FOUND"
  | "SKILL_POLICY_DENIED"
  | "AUTHZ_DENIED"
  | "TOOL_NOT_FOUND"
  | "TOOL_FAILED"
  | "TOOL_DENIED"
  | "MODEL_FAILED"
  | "RUN_NOT_FOUND"
  | "RUN_ALREADY_COMPLETED"
  | "RUN_CANCELLED"
  | "WORKSPACE_ERROR"
  | "PATH_TRAVERSAL_DENIED"
  | "INTERNAL_ERROR"
  | "NOT_IMPLEMENTED";

export class AgentError extends Error {
  readonly code: AgentErrorCode;
  readonly retryable: boolean;

  constructor(code: AgentErrorCode, message: string, retryable = false) {
    super(`[${code}] ${message}`);
    this.name = "AgentError";
    this.code = code;
    this.retryable = retryable;
  }
}
