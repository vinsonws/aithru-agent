import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { SandboxExecutor } from "../../packages/sandbox/src/index.js";

describe("SandboxExecutor", () => {
  const roots: string[] = [];

  afterEach(() => {
    for (const root of roots.splice(0)) {
      rmSync(root, { recursive: true, force: true });
    }
  });

  function createWorkspace(): string {
    const root = mkdtempSync(join(tmpdir(), "aithru-sandbox-test-"));
    roots.push(root);
    return root;
  }

  it("runs node code inside a workspace-scoped cwd", async () => {
    const workspaceRoot = createWorkspace();
    const cwd = join("project", "nested");
    const absoluteCwd = join(workspaceRoot, cwd);
    mkdirSync(absoluteCwd, { recursive: true });
    const executor = new SandboxExecutor({ workspaceRoot });

    const result = await executor.execute({
      runtime: "node",
      cwd,
      code: "console.log(process.cwd())",
    });

    expect(result.exitCode).toBe(0);
    expect(result.stdout.trim()).toBe(absoluteCwd);
    expect(result.stderr).toBe("");
    expect(result.timedOut).toBe(false);
    expect(result.truncated).toBe(false);
  });

  it("truncates output at the configured max byte count", async () => {
    const workspaceRoot = createWorkspace();
    const executor = new SandboxExecutor({ workspaceRoot });

    const result = await executor.execute({
      runtime: "node",
      code: "process.stdout.write('x'.repeat(80))",
      maxOutputBytes: 16,
    });

    expect(result.exitCode).toBe(0);
    expect(result.stdout).toBe("x".repeat(16));
    expect(result.stderr).toBe("");
    expect(result.truncated).toBe(true);
  });

  it("kills commands that exceed the timeout", async () => {
    const workspaceRoot = createWorkspace();
    const executor = new SandboxExecutor({ workspaceRoot });

    const result = await executor.execute({
      runtime: "node",
      code: "setTimeout(() => console.log('late'), 1000)",
      timeoutMs: 50,
    });

    expect(result.timedOut).toBe(true);
    expect(result.exitCode).not.toBe(0);
  });

  it("rejects cwd values that escape the workspace root", async () => {
    const workspaceRoot = createWorkspace();
    const executor = new SandboxExecutor({ workspaceRoot });

    await expect(
      executor.execute({
        runtime: "node",
        cwd: "..",
        code: "console.log('nope')",
      }),
    ).rejects.toThrow(/workspace/i);
  });
});
