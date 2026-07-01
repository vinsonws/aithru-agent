import { describe, it, expect } from "vitest";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES, VISIBILITY } from "@aithru-agent/stream";
import { ProductionCapabilityRouter, TestCapabilityRouter } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { ControlledWebProvider } from "@aithru-agent/external";
import { LocalMemoryProvider } from "@aithru-agent/memory";
import { SkillRegistry, SkillResolver } from "@aithru-agent/skills";
import { writeFileSync, mkdirSync, rmSync } from "fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

function makeSkillDir(): string {
  const dir = join(tmpdir(), `prod_cap_skill_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

function setupSkillRouter(skills: Record<string, string>) {
  const root = makeSkillDir();
  for (const [key, skillMd] of Object.entries(skills)) {
    mkdirSync(join(root, key));
    writeFileSync(join(root, key, "SKILL.md"), skillMd);
  }
  const registry = new SkillRegistry();
  registry.loadBuiltinPackages(root);
  rmSync(root, { recursive: true, force: true });
  const store = new InMemoryStore();
  const eventWriter = new AgentEventWriter(store);
  const resolver = new SkillResolver(registry, store);
  const router = new ProductionCapabilityRouter(store, eventWriter, resolver);
  return { router, store, eventWriter };
}

function activateSkills(
  eventWriter: AgentEventWriter,
  run: AgentRun,
  skills: Array<{ key: string; allowed_tools?: string[]; denied_tools?: string[] }>,
): void {
  for (const skill of skills) {
    eventWriter.write(
      run.id,
      run.thread_id ?? null,
      EVENT_TYPES.SKILL_ACTIVATED,
      {
        key: skill.key,
        trigger: "explicit",
        policy: {
          allowed_tools: skill.allowed_tools ?? [],
          denied_tools: skill.denied_tools ?? [],
        },
      },
      { visibility: VISIBILITY.AUDIT },
    );
  }
}

const READ_SKILL = [
  "---",
  "name: Read Guard",
  "allowed_tools:",
  "  - workspace.list_files",
  "  - workspace.read_file",
  "denied_tools:",
  "  - workspace.delete_file",
  "---",
  "# Read Guard",
].join("\n");

const WRITE_SKILL = [
  "---",
  "name: Write Guard",
  "allowed_tools:",
  "  - workspace.read_file",
  "  - workspace.write_file",
  "denied_tools:",
  "  - workspace.write_file",
  "---",
  "# Write Guard",
].join("\n");

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
    expect(tools.some((t) => t.name === "memory.remember")).toBe(true);
    expect(tools.some((t) => t.name === "web.fetch")).toBe(true);
    expect(tools.some((t) => t.name === "sandbox.execute")).toBe(true);
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

  it("accepts and returns valid preferred_view for workspace.write_file", async () => {
    const tools = await router.listTools({ run });
    const writeTool = tools.find((t) => t.name === "workspace.write_file")!;
    expect((writeTool.input_schema as any).properties.preferred_view.enum).toContain("html_preview");

    const productionResult = await router.executeToolCall(
      {
        id: "tc_write_preferred",
        name: "workspace.write_file",
        input: { path: "/preview.html", content: "<html></html>", preferred_view: "html_preview" },
        run_id: run.id,
      },
      { run },
    );
    expect(productionResult.error).toBeFalsy();
    expect((productionResult.output as any).preferred_view).toBe("html_preview");

    const testStore = new InMemoryStore();
    const testRun: AgentRun = { ...run, id: "r_test_router_preferred", workspace_id: "ws_test_router_preferred" };
    testStore.createRun(testRun);
    const testResult = await new TestCapabilityRouter(testStore).executeToolCall({
      id: "tc_test_write_preferred",
      name: "workspace.write_file",
      input: { path: "/preview.html", content: "<html></html>", preferred_view: "bogus" },
      run_id: testRun.id,
    });
    expect(testResult.error).toBeFalsy();
    expect((testResult.output as any).preferred_view).toBeUndefined();
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

  it("executes memory tools scoped to the run thread", async () => {
    const localStore = new InMemoryStore();
    const localWriter = new AgentEventWriter(localStore);
    const localRouter = new ProductionCapabilityRouter(localStore, localWriter, undefined, {
      memoryProvider: new LocalMemoryProvider(),
    });
    const threadRun: AgentRun = {
      ...run,
      id: "r_memory_thread",
      thread_id: "thread_memory",
      scopes: ["memory:write", "memory:read"],
    };
    const otherThreadRun: AgentRun = {
      ...run,
      id: "r_memory_other",
      thread_id: "thread_other",
      scopes: ["memory:read"],
    };

    await localRouter.executeToolCall(
      { id: "tc_mem_write", name: "memory.remember", input: { key: "color", value: "blue" }, run_id: threadRun.id },
      { run: threadRun },
    );

    const sameThread = await localRouter.executeToolCall(
      { id: "tc_mem_read", name: "memory.recall", input: { key: "color" }, run_id: threadRun.id },
      { run: threadRun },
    );
    const otherThread = await localRouter.executeToolCall(
      { id: "tc_mem_other", name: "memory.recall", input: { key: "color" }, run_id: otherThreadRun.id },
      { run: otherThreadRun },
    );

    expect(sameThread.output).toEqual({ key: "color", value: "blue", found: true });
    expect(otherThread.output).toEqual({ key: "color", value: null, found: false });
  });

  it("executes controlled web fetch and truncates output", async () => {
    const localStore = new InMemoryStore();
    const localWriter = new AgentEventWriter(localStore);
    const localRouter = new ProductionCapabilityRouter(localStore, localWriter, undefined, {
      webProvider: new ControlledWebProvider({
        allowedHosts: ["example.com"],
        fetcher: async (url) => ({
          status: 200,
          text: async () => `content from ${url}`,
        }),
      }),
    });
    const webRun: AgentRun = { ...run, id: "r_web", scopes: ["web:fetch"] };

    const result = await localRouter.executeToolCall(
      { id: "tc_web", name: "web.fetch", input: { url: "https://example.com/a", max_chars: 7 }, run_id: webRun.id },
      { run: webRun },
    );
    const denied = await localRouter.executeToolCall(
      { id: "tc_web_denied", name: "web.fetch", input: { url: "https://evil.test/a" }, run_id: webRun.id },
      { run: webRun },
    );

    expect(result.error).toBeFalsy();
    expect(result.output).toEqual({
      url: "https://example.com/a",
      status: 200,
      content: "content",
      truncated: true,
    });
    expect(denied.error?.message).toContain("WEB_HOST_DENIED");
  });

  it("executes sandbox code inside the run workspace", async () => {
    const localStore = new InMemoryStore();
    const localWriter = new AgentEventWriter(localStore);
    const localRouter = new ProductionCapabilityRouter(localStore, localWriter);
    const sandboxRun: AgentRun = {
      ...run,
      id: "r_sandbox",
      workspace_id: "ws_sandbox",
      scopes: ["sandbox:execute"],
    };
    localStore.createRun(sandboxRun);

    const result = await localRouter.executeToolCall(
      {
        id: "tc_sandbox",
        name: "sandbox.execute",
        input: {
          runtime: "node",
          code: [
            "import { writeFileSync } from 'node:fs';",
            "writeFileSync('sandbox.txt', 'ok');",
            "console.log('done');",
          ].join("\n"),
          max_output_bytes: 32,
        },
        run_id: sandboxRun.id,
      },
      { run: sandboxRun },
    );

    expect(result.error).toBeFalsy();
    expect(result.output).toMatchObject({
      runtime: "node",
      stdout: "done\n",
      stderr: "",
      exit_code: 0,
      timed_out: false,
      truncated: false,
    });
    expect(localStore.readFile(sandboxRun.workspace_id, "/sandbox.txt")?.content).toBe("ok");
  });

  it("redacts sensitive sandbox output before returning it", async () => {
    const localStore = new InMemoryStore();
    const localWriter = new AgentEventWriter(localStore);
    const localRouter = new ProductionCapabilityRouter(localStore, localWriter);
    const sandboxRun: AgentRun = {
      ...run,
      id: "r_sandbox_redact",
      workspace_id: "ws_sandbox_redact",
      scopes: ["sandbox:execute"],
    };
    localStore.createRun(sandboxRun);

    const result = await localRouter.executeToolCall(
      {
        id: "tc_sandbox_redact",
        name: "sandbox.execute",
        input: {
          runtime: "node",
          code: "console.log('token=abc123'); console.error('Bearer abc.def');",
        },
        run_id: sandboxRun.id,
      },
      { run: sandboxRun },
    );

    expect(result.error).toBeFalsy();
    expect(result.output).toMatchObject({
      stdout: "token=[redacted]\n",
      stderr: "Bearer [redacted]\n",
    });
  });

  it("auto-approves later sandbox calls only after the same run has an approved sandbox decision", async () => {
    const localStore = new InMemoryStore();
    const localWriter = new AgentEventWriter(localStore);
    const localRouter = new ProductionCapabilityRouter(localStore, localWriter);
    const sandboxRun: AgentRun = {
      ...run,
      id: "r_sandbox_approval",
      workspace_id: "ws_sandbox_approval",
      scopes: ["sandbox:execute"],
    };
    const otherRun: AgentRun = {
      ...run,
      id: "r_sandbox_other_approval",
      workspace_id: "ws_sandbox_other_approval",
      scopes: ["sandbox:execute"],
    };
    localStore.createRun(sandboxRun);
    localStore.createRun(otherRun);

    const request = {
      id: "tc_sandbox_approval",
      name: "sandbox.execute",
      input: { runtime: "node", code: "console.log('ok')" },
      run_id: sandboxRun.id,
    };
    const first = await localRouter.prepareToolCall(request, { run: sandboxRun });
    localWriter.write(sandboxRun.id, null, EVENT_TYPES.APPROVAL_RESOLVED, {
      approval_id: "aprv_sandbox",
      tool_call_id: request.id,
      name: "sandbox.execute",
      decision: "approved",
    });
    const second = await localRouter.prepareToolCall({ ...request, id: "tc_sandbox_second" }, { run: sandboxRun });
    const other = await localRouter.prepareToolCall({ ...request, id: "tc_sandbox_other", run_id: otherRun.id }, { run: otherRun });

    expect(first.requires_approval).toBe(true);
    expect(second.requires_approval).toBe(false);
    expect(other.requires_approval).toBe(true);
  });

  it("denies deleted artifact tools", async () => {
    const result = await router.prepareToolCall(
      { id: "tc_art", name: "artifact.create", input: {}, run_id: "r1" },
      { run },
    );
    expect(result.allowed).toBe(false);
  });

  it("composes active skill policies from activation events", async () => {
    const { router: skillRouter, store: skillStore, eventWriter: skillWriter } = setupSkillRouter({
      "read-guard": READ_SKILL,
      "write-guard": WRITE_SKILL,
    });
    const skillRun: AgentRun = {
      ...run,
      id: "r_skill_composed",
      workspace_id: "ws_skill_composed",
    };
    skillStore.createRun(skillRun);
    activateSkills(skillWriter, skillRun, [
      {
        key: "read-guard",
        allowed_tools: ["workspace.list_files", "workspace.read_file"],
        denied_tools: ["workspace.delete_file"],
      },
      {
        key: "write-guard",
        allowed_tools: ["workspace.read_file", "workspace.write_file"],
        denied_tools: ["workspace.write_file"],
      },
    ]);

    const tools = await skillRouter.listTools({ run: skillRun });
    expect(tools.map((tool) => tool.name)).toEqual(["workspace.read_file"]);

    const deniedWrite = await skillRouter.prepareToolCall(
      {
        id: "tc_skill_write",
        name: "workspace.write_file",
        input: { path: "/x", content: "y" },
        run_id: skillRun.id,
      },
      { run: skillRun },
    );
    expect(deniedWrite.allowed).toBe(false);
    expect(deniedWrite.reason).toContain('denied by skill policy');

    const deniedList = await skillRouter.prepareToolCall(
      {
        id: "tc_skill_list",
        name: "workspace.list_files",
        input: {},
        run_id: skillRun.id,
      },
      { run: skillRun },
    );
    expect(deniedList.allowed).toBe(false);
    expect(deniedList.reason).toContain('not in skill allow list');
  });
});
