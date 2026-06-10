import { describe, it, expect } from "vitest";
import {
  StaticCapabilityRouter,
  WorkspaceToolAdapter,
  FakeSearchToolAdapter,
  applyAllowedToolsFilter,
} from "../src/index.js";
import type { AgentRunContext } from "../src/index.js";
import { InMemoryWorkspaceProvider } from "@aithru/agent-workspace";
import type { AgentToolCallRequest, ToolCallId, RunId } from "@aithru/agent-core";

function makeContext(overrides?: Partial<AgentRunContext>): AgentRunContext {
  return {
    runId: "run_test" as RunId,
    workspaceId: "ws_test" as unknown as AgentRunContext["workspaceId"],
    actor: {
      actorType: "user",
      orgId: "org_test" as unknown as AgentRunContext["actor"]["orgId"],
      scopes: ["*"],
    },
    ...overrides,
  };
}

function makeToolCall(
  toolName: string,
  input: unknown,
  overrides?: Partial<AgentToolCallRequest>,
): AgentToolCallRequest {
  return {
    id: `tc_${Date.now()}` as ToolCallId,
    toolName,
    input,
    requestedBy: "model",
    ...overrides,
  };
}

describe("StaticCapabilityRouter", () => {
  it("should aggregate tools from all adapters", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
      new FakeSearchToolAdapter(),
    ]);

    const tools = await router.listTools(makeContext());
    const names = tools.map((t) => t.name);

    expect(names).toContain("workspace.listFiles");
    expect(names).toContain("workspace.writeFile");
    expect(names).toContain("fake.search");
    expect(names).toContain("fake.fetch");
  });

  it("should call workspace.readFile through the router (safe tool, no approval needed)", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as unknown as AgentRunContext["actor"]["orgId"] });
    await wsProvider.writeFile({ workspaceId: ws.id, path: "/test/hello.md", content: "# Hello" });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.callTool(
      makeToolCall("workspace.readFile", { path: "/test/hello.md" }),
      makeContext({ workspaceId: ws.id }),
    );

    expect(result.status).toBe("completed");
  });

  it("should return waiting_approval for write-risk tool even with scopes", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as unknown as AgentRunContext["actor"]["orgId"] });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.callTool(
      makeToolCall("workspace.writeFile", {
        path: "/test/hello.md",
        content: "# Hello",
      }),
      makeContext({ workspaceId: ws.id }),
    );

    expect(result.status).toBe("waiting_approval");
  });

  it("should not bypass approval when alreadyApproved is set by a non-harness caller", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as unknown as AgentRunContext["actor"]["orgId"] });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.callTool(
      makeToolCall("workspace.writeFile", { path: "/test/hello.md", content: "# Hello" }, { alreadyApproved: true }),
      makeContext({ workspaceId: ws.id }),
    );

    expect(result.status).toBe("waiting_approval");
  });

  it("should bypass approval only for harness resume calls", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as unknown as AgentRunContext["actor"]["orgId"] });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.callTool(
      makeToolCall("workspace.writeFile", { path: "/test/hello.md", content: "# Hello" }, {
        alreadyApproved: true,
        requestedBy: "harness",
      }),
      makeContext({ workspaceId: ws.id }),
    );

    expect(result.status).toBe("completed");
    expect(result.workspaceChanges).toHaveLength(1);
  });

  it("should return normalized workspace change paths", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as unknown as AgentRunContext["actor"]["orgId"] });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.callTool(
      makeToolCall("workspace.writeFile", { path: "/reports/../reports/result.md", content: "# Hello" }, {
        alreadyApproved: true,
        requestedBy: "harness",
      }),
      makeContext({ workspaceId: ws.id }),
    );

    expect(result.workspaceChanges).toEqual([{ path: "/reports/result.md", operation: "created" }]);
  });

  it("should deny tool when required scopes are missing", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as unknown as AgentRunContext["actor"]["orgId"] });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.callTool(
      makeToolCall("workspace.writeFile", { path: "/test/hello.md", content: "# Hello" }),
      // No "*" scope and no "workspace:write" scope
      makeContext({ workspaceId: ws.id, actor: { actorType: "user", orgId: "org_t" as unknown as AgentRunContext["actor"]["orgId"], scopes: ["workspace:read"] } }),
    );

    expect(result.status).toBe("denied");
    expect(result.error?.code).toBe("AUTHZ_DENIED");
  });

  it("should return denied for unknown tool", async () => {
    const router = new StaticCapabilityRouter([]);

    const result = await router.callTool(
      makeToolCall("nonexistent.tool", {}),
      makeContext(),
    );

    expect(result.status).toBe("denied");
    expect(result.error?.code).toBe("TOOL_NOT_FOUND");
  });

  // ── Two-phase prepare / execute tests ─────────────────────────────────

  it("prepareToolCall safe tool returns ready and does not execute", async () => {
    let adapterCalled = false;
    const wsProvider = new InMemoryWorkspaceProvider();
    const adapter = new (class extends WorkspaceToolAdapter {
      constructor() { super(wsProvider); }
      async callTool(req: any, desc: any, ctx: any) {
        adapterCalled = true;
        return super.callTool(req, desc, ctx);
      }
    })();
    const router = new StaticCapabilityRouter([adapter]);

    const result = await router.prepareToolCall(
      makeToolCall("workspace.listFiles", {}),
      makeContext(),
    );

    expect(result.status).toBe("ready");
    expect(adapterCalled).toBe(false);
  });

  it("prepareToolCall write tool returns waiting_approval", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.prepareToolCall(
      makeToolCall("workspace.writeFile", { path: "/test.md", content: "data" }),
      makeContext(),
    );

    expect(result.status).toBe("waiting_approval");
  });

  it("prepareToolCall unknown tool returns denied", async () => {
    const router = new StaticCapabilityRouter([]);

    const result = await router.prepareToolCall(
      makeToolCall("nonexistent.tool", {}),
      makeContext(),
    );

    expect(result.status).toBe("denied");
    if (result.status === "denied") {
      expect(result.error?.code).toBe("TOOL_NOT_FOUND");
    }
  });

  it("executeToolCall safe tool returns completed", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as any });
    await wsProvider.writeFile({ workspaceId: ws.id, path: "/test.md", content: "# Hello" });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.executeToolCall(
      makeToolCall("workspace.readFile", { path: "/test.md" }),
      makeContext({ workspaceId: ws.id }),
    );

    expect(result.status).toBe("completed");
  });

  it("executeToolCall write tool + harness alreadyApproved returns completed", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as any });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.executeToolCall(
      makeToolCall("workspace.writeFile", { path: "/test.md", content: "# Hello" }, {
        alreadyApproved: true,
        requestedBy: "harness",
      }),
      makeContext({ workspaceId: ws.id }),
    );

    expect(result.status).toBe("completed");
  });

  it("executeToolCall write tool + model alreadyApproved returns waiting_approval", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as any });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.executeToolCall(
      makeToolCall("workspace.writeFile", { path: "/test.md", content: "# Hello" }, {
        alreadyApproved: true,
        requestedBy: "model",
      }),
      makeContext({ workspaceId: ws.id }),
    );

    expect(result.status).toBe("waiting_approval");
  });
});

describe("applyAllowedToolsFilter", () => {
  it("should return empty array when allowed list is empty", () => {
    const descriptors: Parameters<typeof applyAllowedToolsFilter>[0] = [
      { name: "workspace.readFile", description: "Read files", kind: "workspace", requiredScopes: [], riskLevel: "safe", approvalPolicy: "never" },
    ];

    const result = applyAllowedToolsFilter(descriptors, []);
    expect(result).toEqual([]);
  });

  it("should filter to only allowed tools", () => {
    const descriptors: Parameters<typeof applyAllowedToolsFilter>[0] = [
      { name: "workspace.readFile", description: "Read files", kind: "workspace", requiredScopes: [], riskLevel: "safe", approvalPolicy: "never" },
      { name: "workspace.writeFile", description: "Write files", kind: "workspace", requiredScopes: [], riskLevel: "write", approvalPolicy: "on_risk" },
      { name: "fake.search", description: "Fake search", kind: "subsystem_api", requiredScopes: [], riskLevel: "safe", approvalPolicy: "never" },
    ];

    const result = applyAllowedToolsFilter(descriptors, ["workspace.readFile"]);
    expect(result).toHaveLength(1);
    expect(result[0]!.name).toBe("workspace.readFile");
  });
});
