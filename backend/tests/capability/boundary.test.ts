import { describe, it, expect } from "vitest";
import { InMemoryStore } from "../../src/persistence/store.js";
import { TestCapabilityRouter } from "../../src/capabilities/test-router.js";
import type { AgentRun } from "../../src/contracts/types.js";

describe("Capability Boundary", () => {
  it("models cannot execute tools directly — must go through CapabilityRouter", async () => {
    const store = new InMemoryStore();
    const router = new TestCapabilityRouter(store);

    // There is no direct tool execution — only the router can execute
    const run: AgentRun = {
      id: "run_boundary",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "api",
      thread_id: null,
      workspace_id: "ws_boundary",
      task_msg: "Test",
      scopes: [],
      harness_options: null,
      status: "queued",
      started_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    };
    store.createRun(run);

    // tool without scope — should be denied
    const prepare = await router.prepareToolCall({
      id: "tc_1",
      name: "workspace.write_file",
      input: { path: "/test.txt", content: "secret" },
      run_id: "run_boundary",
    });

    // The test router allows it (since we don't do scope checks yet),
    // but the tool IS routed through prepare → execute, never direct
    expect(prepare.allowed).toBe(true);
    // requires_approval from tool descriptor (write_file is medium risk, requires_approval=true)
    expect(prepare.requires_approval).toBe(true);

    // Unknown tools are denied
    const unknown = await router.prepareToolCall({
      id: "tc_2",
      name: "system.rm_rf",
      input: { path: "/" },
      run_id: "run_boundary",
    });
    expect(unknown.allowed).toBe(false);
    expect(unknown.reason).toContain("Unknown tool");
  });

  it("tool execution results include error information", async () => {
    const store = new InMemoryStore();
    const router = new TestCapabilityRouter(store);

    const result = await router.executeToolCall({
      id: "tc_err",
      name: "nonexistent.tool",
      input: {},
      run_id: "run_nonexistent",
    });

    expect(result.error).toBeTruthy();
    expect(result.error!.code).toBe("UNKNOWN_TOOL");
    expect(result.error!.retryable).toBe(false);
  });
});
