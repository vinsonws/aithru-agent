import { describe, it, expect } from "vitest";
import {
  InMemoryWorkspaceProvider,
  normalizePath,
  workspaceKey,
} from "../src/index.js";
import type { OrgId, WorkspaceId } from "@aithru/agent-core";
import { AgentError } from "@aithru/agent-core";

describe("normalizePath", () => {
  it("should normalize a simple path", () => {
    expect(normalizePath("/foo/bar")).toBe("/foo/bar");
  });

  it("should collapse repeated slashes", () => {
    expect(normalizePath("/foo//bar///baz")).toBe("/foo/bar/baz");
  });

  it("should resolve single dot", () => {
    expect(normalizePath("/foo/./bar")).toBe("/foo/bar");
  });

  it("should resolve double dot", () => {
    expect(normalizePath("/foo/bar/../baz")).toBe("/foo/baz");
  });

  it("should reject traversal above root", () => {
    expect(() => normalizePath("/../etc/passwd")).toThrow(AgentError);
    expect(() => normalizePath("/foo/../../etc")).toThrow(AgentError);
  });

  it("should convert backslashes", () => {
    expect(normalizePath("\\foo\\bar")).toBe("/foo/bar");
  });
});

describe("workspaceKey", () => {
  it("should prefix a user path with the workspace id", () => {
    expect(workspaceKey("ws_1", "/foo/bar")).toBe("/ws_1/foo/bar");
  });

  it("should reject path traversal that escapes the user path", () => {
    expect(() => workspaceKey("ws_1", "/../etc/passwd")).toThrow(AgentError);
  });

  it("should reject path traversal that tries to reach another workspace", () => {
    // /../ws_2/secret.txt would resolve to /ws_2/secret.txt if not checked
    expect(() => workspaceKey("ws_1", "/../ws_2/secret.txt")).toThrow(AgentError);
  });
});

describe("InMemoryWorkspaceProvider", () => {
  it("should create a workspace", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    expect(ws.orgId).toBe("org_1");
    expect(ws.storageBackend).toBe("memory");
    expect(ws.id).toBeTruthy();
  });

  it("should write and read a file", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    await provider.writeFile({
      workspaceId: ws.id,
      path: "/test/hello.txt",
      content: "Hello, World!",
    });

    const file = await provider.readFile(ws.id, "/test/hello.txt");
    expect(file.content).toBe("Hello, World!");
  });

  it("should list files after writing", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    await provider.writeFile({
      workspaceId: ws.id,
      path: "/reports/report.md",
      content: "# Report",
    });

    const files = await provider.listFiles(ws.id);
    expect(files.length).toBeGreaterThanOrEqual(1);
  });

  it("should list files in a subdirectory", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    await provider.writeFile({ workspaceId: ws.id, path: "/reports/summary.md", content: "# Summary" });
    await provider.writeFile({ workspaceId: ws.id, path: "/reports/details/report.md", content: "# Details" });
    await provider.writeFile({ workspaceId: ws.id, path: "/scratch/tmp.txt", content: "tmp" });

    const reports = await provider.listFiles(ws.id, "/reports");
    expect(reports.length).toBeGreaterThanOrEqual(2);

    const scratch = await provider.listFiles(ws.id, "/scratch");
    expect(scratch).toHaveLength(1);
  });

  it("should not include files from similarly prefixed workspaces", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws1 = await provider.createWorkspace({ orgId: "org_1" as OrgId });
    const ws2 = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    await provider.writeFile({ workspaceId: ws1.id, path: "/visible.txt", content: "visible" });
    await provider.writeFile({ workspaceId: `${ws1.id}0` as WorkspaceId, path: "/leaked.txt", content: "leaked" });
    await provider.writeFile({ workspaceId: ws2.id, path: "/other.txt", content: "other" });

    const files = await provider.listFiles(ws1.id);

    expect(files.map((f) => f.path)).toEqual(["/visible.txt"]);
  });

  it("should not include files from similarly prefixed directories", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    await provider.writeFile({ workspaceId: ws.id, path: "/reports/summary.md", content: "# Summary" });
    await provider.writeFile({ workspaceId: ws.id, path: "/reports-old/summary.md", content: "# Old" });

    const files = await provider.listFiles(ws.id, "/reports");

    expect(files.map((f) => f.path)).toEqual(["/summary.md"]);
  });

  it("should reject cross-workspace path traversal", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws1 = await provider.createWorkspace({ orgId: "org_1" as OrgId });
    const ws2 = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    // Write to ws2
    await provider.writeFile({ workspaceId: ws2.id, path: "/secret.txt", content: "secret" });

    // Try to read ws2's file from ws1 via path traversal
    await expect(
      provider.readFile(ws1.id, "/../" + ws2.id.slice(1) + "/secret.txt"),
    ).rejects.toThrow(AgentError);
  });

  it("should reject path traversal on write", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    await expect(
      provider.writeFile({
        workspaceId: ws.id,
        path: "/../../etc/passwd",
        content: "hack",
      }),
    ).rejects.toThrow(AgentError);
  });

  it("should delete a file", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    await provider.writeFile({
      workspaceId: ws.id,
      path: "/scratch/tmp.txt",
      content: "temp",
    });

    await provider.deleteFile(ws.id, "/scratch/tmp.txt");

    await expect(provider.readFile(ws.id, "/scratch/tmp.txt")).rejects.toThrow(
      AgentError,
    );
  });

  it("should throw on reading non-existent file", async () => {
    const provider = new InMemoryWorkspaceProvider();
    const ws = await provider.createWorkspace({ orgId: "org_1" as OrgId });

    await expect(provider.readFile(ws.id, "/nonexistent.txt")).rejects.toThrow(
      AgentError,
    );
  });
});
