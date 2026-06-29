import { describe, expect, it } from "vitest";
import { ModelProfileRegistry } from "@aithru-agent/model";

describe("ModelProfileRegistry", () => {
  it("resolves enabled profiles when scopes and capabilities match", () => {
    const registry = new ModelProfileRegistry();
    registry.register({
      key: "default",
      provider: "openai",
      model: "gpt-test",
      enabled: true,
      required_scopes: ["model:use"],
      capabilities: ["tool_calls"],
    });

    const profile = registry.resolve({
      key: "default",
      run_scopes: ["model:use"],
      requested_capabilities: ["tool_calls"],
    });

    expect(profile.model).toBe("gpt-test");
  });

  it("denies disabled or unauthorized profiles", () => {
    const registry = new ModelProfileRegistry();
    registry.register({
      key: "locked",
      provider: "anthropic",
      model: "claude-test",
      enabled: false,
      required_scopes: ["model:use"],
      capabilities: [],
    });

    expect(() =>
      registry.resolve({ key: "locked", run_scopes: ["*"] }),
    ).toThrow("MODEL_PROFILE_DISABLED");

    registry.register({
      key: "scoped",
      provider: "openai",
      model: "gpt-test",
      enabled: true,
      required_scopes: ["model:admin"],
      capabilities: [],
    });

    expect(() =>
      registry.resolve({ key: "scoped", run_scopes: ["model:use"] }),
    ).toThrow("MODEL_PROFILE_SCOPE_DENIED");
  });
});
