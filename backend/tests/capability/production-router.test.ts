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
    expect(tools.length).toBeGreaterThanOrEqual(6);
    expect(tools.some((t) => t.name === "artifact.create")).toBe(false);
    expect(tools.some((t) => t.name === "presentation.present")).toBe(true);
    const presentTool = tools.find((t) => t.name === "presentation.present")!;
    expect(presentTool.description).toContain("final primary output");
    expect(presentTool.description).toContain("user decision");
    expect(presentTool.description).toContain("Do not present temporary");
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

  it("auto-presents explicitly requested written workspace files without opening preview", async () => {
    const localStore = new InMemoryStore();
    const localWriter = new AgentEventWriter(localStore);
    const localRouter = new ProductionCapabilityRouter(localStore, localWriter);
    const localRun: AgentRun = {
      ...run,
      id: "r_write_present",
      thread_id: "thread_write_present",
      workspace_id: "ws_write_present",
      task_msg: "你在本地创建一个文件 hello.txt 内容是： 第一",
    };
    localStore.createRun(localRun);

    const result = await localRouter.executeToolCall(
      {
        id: "tc_write_present",
        name: "workspace.write_file",
        input: { path: "hello.txt", content: "第一" },
        run_id: localRun.id,
      },
      { run: localRun },
    );

    expect(result.error).toBeFalsy();
    const event = localStore.listEvents(localRun.id).find((item) => item.type === "presentation.created");
    expect(event?.payload).toMatchObject({
      presentation: {
        title: "hello.txt",
        resource: { kind: "workspace_file", path: "/hello.txt" },
        surfaces: ["conversation"],
        preferred_view: "source_text",
        effects: undefined,
        source: {
          created_by: "tool",
          tool_call_id: "tc_write_present",
          tool_name: "workspace.write_file",
        },
      },
    });
  });

  it("does not auto-present unmentioned written workspace files", async () => {
    const localStore = new InMemoryStore();
    const localWriter = new AgentEventWriter(localStore);
    const localRouter = new ProductionCapabilityRouter(localStore, localWriter);
    const localRun: AgentRun = {
      ...run,
      id: "r_write_quiet",
      workspace_id: "ws_write_quiet",
      task_msg: "run backup",
    };
    localStore.createRun(localRun);

    await localRouter.executeToolCall(
      {
        id: "tc_write_quiet",
        name: "workspace.write_file",
        input: { path: "/tmp/chunk-001.json", content: "{}" },
        run_id: localRun.id,
      },
      { run: localRun },
    );

    expect(localStore.listEvents(localRun.id).some((item) => item.type === "presentation.created")).toBe(false);
  });

  it("presents existing workspace files as trusted stream events", async () => {
    const localStore = new InMemoryStore();
    const localWriter = new AgentEventWriter(localStore);
    const localRouter = new ProductionCapabilityRouter(localStore, localWriter);
    const localRun: AgentRun = {
      ...run,
      id: "r_present",
      thread_id: "thread_1",
      workspace_id: "ws_present",
    };
    localStore.createRun(localRun);
    localStore.writeFile("ws_present", "/outputs/backup.md", "# Backup");

    const result = await localRouter.executeToolCall(
      {
        id: "tc_present",
        name: "presentation.present",
        input: {
          resources: [
            {
              kind: "workspace_file",
              path: "/outputs/backup.md",
              title: "Backup report",
              preferred_view: "markdown",
              surfaces: ["conversation", "side_panel"],
              effects: [{ kind: "open_panel", panel: "preview", mode: "soft" }],
            },
          ],
        },
        run_id: localRun.id,
      },
      { run: localRun },
    );

    expect(result.error).toBeFalsy();
    expect((result.output as any).presentations).toHaveLength(1);
    const event = localStore.listEvents(localRun.id).find((item) => item.type === "presentation.created");
    expect(event?.payload).toMatchObject({
      presentation: {
        run_id: localRun.id,
        thread_id: "thread_1",
        title: "Backup report",
        resource: { kind: "workspace_file", path: "/outputs/backup.md" },
        preferred_view: "markdown",
        available_views: expect.arrayContaining(["markdown", "source_text", "download"]),
        surfaces: ["conversation", "side_panel"],
        effects: [{ kind: "open_panel", panel: "preview", mode: "soft" }],
        metadata: { workspace_id: "ws_present" },
        source: {
          created_by: "model_request",
          tool_call_id: "tc_present",
          tool_name: "presentation.present",
        },
      },
    });
  });

  it("rejects missing workspace file presentations", async () => {
    const result = await router.executeToolCall(
      {
        id: "tc_missing",
        name: "presentation.present",
        input: { resources: [{ kind: "workspace_file", path: "/missing.md" }] },
        run_id: run.id,
      },
      { run },
    );

    expect(result.error).toBeTruthy();
    expect(result.error?.message).toContain("File not found");
  });

  it("denies deleted artifact tools", async () => {
    const result = await router.prepareToolCall(
      { id: "tc_art", name: "artifact.create", input: {}, run_id: "r1" },
      { run },
    );
    expect(result.allowed).toBe(false);
  });
});
