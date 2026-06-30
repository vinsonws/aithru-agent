import { describe, it, expect } from "vitest";
import { PolicyEngine, resolveSkillPolicy, checkScopes } from "@aithru-agent/capabilities";
import type { AgentToolDescriptor } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";

function createRun(scopes: string[]): AgentRun {
  return {
    id: "run_test", org_id: "org_1", actor_user_id: "u1",
    source: "api", thread_id: null, workspace_id: "ws_1",
    task_msg: "test", scopes, harness_options: null,
    status: "running", started_at: "2026-01-01T00:00:00Z",
    completed_at: null, claim: null, result: null, error: null,
  };
}

function createTool(name: string, scopes: string[], risk: "low"|"medium"|"high" = "low", approval = false): AgentToolDescriptor {
  return { name, description: "test", risk_level: risk, requires_approval: approval, required_scopes: scopes, input_schema: {} };
}

describe("checkScopes", () => {
  it("allows wildcard scope", () => {
    const result = checkScopes(createTool("t", ["x"]), createRun(["*"]));
    expect(result.allowed).toBe(true);
  });

  it("allows matching scope", () => {
    const result = checkScopes(createTool("t", ["workspace:read"]), createRun(["workspace:read"]));
    expect(result.allowed).toBe(true);
  });

  it("allows frontend agent-prefixed scope aliases", () => {
    expect(checkScopes(createTool("read", ["workspace:read"]), createRun(["agent.workspace.read"])).allowed).toBe(true);
    expect(checkScopes(createTool("write", ["workspace:write"]), createRun(["agent.workspace.write"])).allowed).toBe(true);
    expect(checkScopes(createTool("todo", ["todo:write"]), createRun(["agent.todo.write"])).allowed).toBe(true);
  });

  it("denies missing scope", () => {
    const result = checkScopes(createTool("t", ["admin"]), createRun(["user"]));
    expect(result.allowed).toBe(false);
    expect(result.missing_scopes).toContain("admin");
  });
});

describe("PolicyEngine", () => {
  it("denies tool on deny list", () => {
    const engine = new PolicyEngine(
      { allowedTools: new Set(), deniedTools: new Set(["dangerous.tool"]) },
      createRun(["*"]),
    );
    const result = engine.checkToolCall(createTool("dangerous.tool", []), {
      id: "tc", name: "dangerous.tool", input: {}, run_id: "r1",
    });
    expect(result.allowed).toBe(false);
    expect(result.audit_event_type).toBe("tool.skill_denied");
  });

  it("denies tool not in allow list", () => {
    const engine = new PolicyEngine(
      { allowedTools: new Set(["safe.tool"]), deniedTools: new Set() },
      createRun(["*"]),
    );
    const result = engine.checkToolCall(createTool("other.tool", []), {
      id: "tc", name: "other.tool", input: {}, run_id: "r1",
    });
    expect(result.allowed).toBe(false);
  });

  it("denies tool without required scope", () => {
    const engine = new PolicyEngine(
      { allowedTools: new Set(["admin.tool"]), deniedTools: new Set() },
      createRun(["user"]),
    );
    const result = engine.checkToolCall(
      createTool("admin.tool", ["admin"]),
      { id: "tc", name: "admin.tool", input: {}, run_id: "r1" },
    );
    expect(result.allowed).toBe(false);
    expect(result.audit_event_type).toBe("tool.scope_denied");
  });

  it("marks approval required for write tools without auto-approve scope", () => {
    const engine = new PolicyEngine(
      { allowedTools: new Set(), deniedTools: new Set() },
      createRun(["workspace:write"]),
    );
    const result = engine.checkToolCall(
      createTool("workspace.write_file", ["workspace:write"], "medium", true),
      { id: "tc", name: "workspace.write_file", input: {}, run_id: "r1" },
    );
    expect(result.allowed).toBe(true);
    expect(result.requires_approval).toBe(true);
  });

  it("auto-approves wildcard-scoped internal runs", () => {
    const engine = new PolicyEngine(
      { allowedTools: new Set(), deniedTools: new Set() },
      createRun(["*"]),
    );
    const result = engine.checkToolCall(
      createTool("workspace.write_file", ["workspace:write"], "medium", true),
      { id: "tc", name: "workspace.write_file", input: {}, run_id: "r1" },
    );
    expect(result.allowed).toBe(true);
    expect(result.requires_approval).toBe(false);
  });
});
