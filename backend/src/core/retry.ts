export interface AgentRunRetryPolicy {
  max_attempts: number;
  initial_delay_seconds: number;
  max_delay_seconds: number;
  backoff_multiplier: number;
}

export interface AgentRunRetryState {
  attempt: number;
  next_retry_at: string | null;
  last_error?: { code: string; message: string };
}

export function createDefaultRetryPolicy(): AgentRunRetryPolicy {
  return {
    max_attempts: 3,
    initial_delay_seconds: 0,
    max_delay_seconds: 300,
    backoff_multiplier: 2.0,
  };
}

export function canRetry(
  policy: AgentRunRetryPolicy,
  state: AgentRunRetryState,
): boolean {
  return state.attempt < policy.max_attempts;
}

export function delaySecondsForAttempt(
  policy: AgentRunRetryPolicy,
  attempt: number,
): number {
  if (attempt <= 1) return policy.initial_delay_seconds;
  const delay =
    policy.initial_delay_seconds * Math.pow(policy.backoff_multiplier, attempt - 1);
  return Math.min(policy.max_delay_seconds, Math.floor(delay));
}

export function nextRetryAt(
  policy: AgentRunRetryPolicy,
  state: AgentRunRetryState,
): string {
  const base = state.next_retry_at
    ? new Date(state.next_retry_at)
    : new Date();
  const delay = delaySecondsForAttempt(policy, state.attempt + 1);
  return new Date(base.getTime() + delay * 1000)
    .toISOString()
    .replace(/\.\d{3}/, "");
}
