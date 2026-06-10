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

  it("should bypass approval check when alreadyApproved flag is set", async () => {
    const wsProvider = new InMemoryWorkspaceProvider();
    const ws = await wsProvider.createWorkspace({ orgId: "org_t" as unknown as AgentRunContext["actor"]["orgId"] });
    const router = new StaticCapabilityRouter([
      new WorkspaceToolAdapter(wsProvider),
    ]);

    const result = await router.callTool(
      makeToolCall("workspace.writeFile", { path: "/test/hello.md", content: "# Hello" }, { alreadyApproved: true }),
      makeContext({ workspaceId: ws.id }),
    );

    // Should complete instead of returning waiting_approval
    expect(result.status).toBe("completed");
    expect(result.workspaceChanges).toHaveLength(1);
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
