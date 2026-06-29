import { describe, it, expect } from "vitest";
import { redactPayload, REDACTED_VALUE } from "@aithru-agent/stream";

describe("redactPayload", () => {
  it("returns unchanged for 'none' redaction", () => {
    const payload = { secret: "s3cr3t", data: "hello" };
    expect(redactPayload(payload, "none")).toEqual(payload);
  });

  it("returns REDACTED_VALUE for 'full' redaction", () => {
    expect(redactPayload({ a: 1 }, "full")).toBe(REDACTED_VALUE);
  });

  it("redacts sensitive fields in 'partial' mode", () => {
    const result = redactPayload({ token: "abc123", name: "test" }, "partial") as any;
    expect(result.token).toBe(REDACTED_VALUE);
    expect(result.name).toBe("test");
  });

  it("redacts nested sensitive fields", () => {
    // "config" is not a sensitive key, but "api_key" nested under it IS
    const result = redactPayload({ config: { api_key: "key", user: "u" } }, "partial") as any;
    expect(result.config.api_key).toBe(REDACTED_VALUE);
    expect(result.config.user).toBe("u");
  });

  it("handles arrays", () => {
    const result = redactPayload([{ secret: "x" }, { name: "y" }], "partial") as any;
    expect(result[0].secret).toBe(REDACTED_VALUE);
    expect(result[1].name).toBe("y");
  });
});
