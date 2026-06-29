export interface AgentErrorPayload {
  code: string;
  message: string;
  retryable: boolean;
  details?: unknown;
}

export class AgentError extends Error {
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly details?: unknown;

  constructor(code: string, message: string, retryable = false, details?: unknown) {
    super(message);
    this.name = "AgentError";
    this.code = code;
    this.retryable = retryable;
    this.details = details;
  }
}
