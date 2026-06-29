// backend/src/stream/redaction.ts

export const REDACTED_VALUE = "***REDACTED***";

// Fields that should always be redacted from event payloads
const SENSITIVE_FIELD_PATTERNS = [
  /secret/i,
  /token/i,
  /password/i,
  /credential/i,
  /api[_-]?key/i,
  /auth/i,
];

function isSensitiveKey(key: string): boolean {
  return SENSITIVE_FIELD_PATTERNS.some((p) => p.test(key));
}

function deepRedact(obj: unknown, depth: number = 0): unknown {
  if (depth > 20) return REDACTED_VALUE; // safety limit
  if (obj === null || obj === undefined) return obj;
  if (typeof obj === "string") return obj;
  if (typeof obj !== "object") return obj;

  if (Array.isArray(obj)) {
    return obj.map((item) => deepRedact(item, depth + 1));
  }

  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
    if (isSensitiveKey(key)) {
      result[key] = REDACTED_VALUE;
    } else if (typeof value === "object" && value !== null) {
      result[key] = deepRedact(value, depth + 1);
    } else {
      result[key] = value;
    }
  }
  return result;
}

export function redactPayload(payload: unknown, redactionLevel: "none" | "partial" | "full"): unknown {
  if (redactionLevel === "none") return payload;
  if (redactionLevel === "full") return REDACTED_VALUE;
  return deepRedact(payload);
}
