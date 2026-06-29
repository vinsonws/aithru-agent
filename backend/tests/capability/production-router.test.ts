import { describe, it, expect } from "vitest";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter } from "@aithru-agent/stream";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";

describe("ProductionCapabilityRouter", () => {
  const store = new InMemoryStore();
  const eventWriter = new AgentEventWriter(store);
  const router = new ProductionCapabilityRouter(store, eventWriter);
  const run: AgentRun = {
    id: "r1", org_id: "o1", actor_user_id: "u1", source: "api",
    thread_id: null, workspace_id: "ws1", task_msg: "test",
    scopes: ["*"], harness_options: null, status: "running",
    started_at: "2026-01-01T00:00:00Z", completed_at: null, claim: null, result: null, error: null,
  };
  store.createRun(run);

  it("lists all production tools", async () => {
    const tools = await router.listTools({ run });
    expect(tools.length).toBeGreaterThanOrEqual(8);
    expect(tools.some((t) => t.name === "artifact.create")).toBe(true);
  });

  it("denies unknown tools", async () => {
    const result = await router.prepareToolCall(
      { id: "tc", name: "hack.tool", input: {}, run_id: "r1" },
      { run },
    );
    expect(result.allowed).toBe(false);
  });

  it("requires approval for write_file", async () => {
    const approvalRun: AgentRun = {
      ...run,
      id: "r1_write_scoped",
      scopes: ["workspace:write"],
    };
    store.createRun(approvalRun);
    const result = await router.prepareToolCall(
      { id: "tc", name: "workspace.write_file", input: { path: "/x", content: "y" }, run_id: approvalRun.id },
      { run: approvalRun },
    );
    expect(result.allowed).toBe(true);
    expect(result.requires_approval).toBe(true);
  });

  it("executes workspace.read_file", async () => {
    store.writeFile("ws1", "/test.txt", "content");
    const result = await router.executeToolCall(
      { id: "tc", name: "workspace.read_file", input: { path: "/test.txt" }, run_id: "r1" },
      { run },
    );
    expect(result.error).toBeFalsy();
    expect((result.output as any).content).toBe("content");
  });

  it("executes artifact.create and artifact.finalize", async () => {
    const createResult = await router.executeToolCall(
      { id: "tc_art", name: "artifact.create", input: { title: "Report", content_type: "text/markdown", content: "# Hi" }, run_id: "r1" },
      { run },
    );
    expect(createResult.error).toBeFalsy();
    const artifactId = (createResult.output as any).id;

    const finalizeResult = await router.executeToolCall(
      { id: "tc_fin", name: "artifact.finalize", input: { artifact_id: artifactId }, run_id: "r1" },
      { run },
    );
    expect((finalizeResult.output as any).status).toBe("finalized");
  });
});
