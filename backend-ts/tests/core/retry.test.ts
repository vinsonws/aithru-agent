import { describe, it, expect } from "vitest";
import {
  createDefaultRetryPolicy,
  canRetry,
  delaySecondsForAttempt,
} from "../../src/core/retry.js";

describe("RetryPolicy", () => {
  it("allows retries within max_attempts", () => {
    const policy = createDefaultRetryPolicy();
    expect(canRetry(policy, { attempt: 0, next_retry_at: null })).toBe(true);
    expect(canRetry(policy, { attempt: 2, next_retry_at: null })).toBe(true);
    expect(canRetry(policy, { attempt: 3, next_retry_at: null })).toBe(false);
  });

  it("calculates exponential backoff", () => {
    const policy = {
      max_attempts: 5,
      initial_delay_seconds: 10,
      max_delay_seconds: 300,
      backoff_multiplier: 2,
    };
    expect(delaySecondsForAttempt(policy, 1)).toBe(10);
    expect(delaySecondsForAttempt(policy, 2)).toBe(20);
    expect(delaySecondsForAttempt(policy, 3)).toBe(40);
    expect(delaySecondsForAttempt(policy, 10)).toBeLessThanOrEqual(300);
  });
});
