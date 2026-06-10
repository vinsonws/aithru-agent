import { describe, it, expect, vi } from "vitest";
import {
  NativeHarnessEngine,
  ScriptedModelPort,
} from "../src/index.js";
import type { AgentHarnessEnginePorts, AgentSkillResolver } from "../src/index.js";
import {
  AgentEventWriter,
  InMemoryAgentEventStore,
  InMemoryAgentEventBus,
} from "@aithru/agent-stream";
import { InMemoryWorkspaceProvider } from "@aithru/agent-workspace";
import { StaticCapabilityRouter, WorkspaceToolAdapter, FakeSearchToolAdapter } from "@aithru/agent-tools";
import type { AgentSkill, OrgId, SkillId, UserId, RunId } from "@aithru/agent-core";
import type { AgentSkillManifest } from "@aithru/agent-skills";

function createTestPorts(): AgentHarnessEnginePorts & { eventBus: InMemoryAgentEventBus } {
  const store = new InMemoryAgentEventStore();
  const bus = new InMemoryAgentEventBus();
  const writer = new AgentEventWriter(store, bus);
  const workspaceProvider = new InMemoryWorkspaceProvider();
  const capabilityRouter = new StaticCapabilityRouter([
    new WorkspaceToolAdapter(workspaceProvider),
    new FakeSearchToolAdapter(),
  ]);

  const skillResolver: AgentSkillResolver = {
    async resolve(_skillIdOrKey: string) {
      return null;
    },
    async resolveFromManifest(_manifest: AgentSkillManifest, _orgId: OrgId) {
      throw new Error("Not implemented");
    },
  };

  const model = new ScriptedModelPort();

  return {
    eventWriter: writer,
    workspaceProvider,
    capabilityRouter,
    skillResolver,
    model,
    eventBus: bus,
  };
}

describe("NativeHarnessEngine", () => {
  it("should produce lifecycle events and pause for approval on write tool", async () => {
    const ports = createTestPorts();
    const engine = new NativeHarnessEngine(ports);

    const events = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Run a test",
    })) {
      events.push(event);
    }

    const types = events.map((e) => e.type);
    expect(types).toContain("run.created");
    expect(types).toContain("run.started");
    expect(types).toContain("message.created");
    expect(types).toContain("message.delta");
    expect(types).toContain("todo.created");
    expect(types).toContain("model.started");
    expect(types).toContain("tool.proposed");
    expect(types).toContain("approval.requested");
    expect(types).toContain("run.paused");
    expect(types).not.toContain("tool.started");
    expect(types).not.toContain("tool.completed");
    expect(types).not.toContain("run.completed");
  });

  it("should route safe tool calls through capability router", async () => {
    const ports = createTestPorts();
    ports.model = new ScriptedModelPort([
      { type: "tool", name: "workspace.listFiles", input: {} },
      { type: "finish" },
    ]);
    const engine = new NativeHarnessEngine(ports);

    const events = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "List files",
    })) {
      events.push(event);
    }

    const toolCompleted = events.filter((e) => e.type === "tool.completed");
    expect(toolCompleted.length).toBeGreaterThanOrEqual(1);
    expect(events.some((e) => e.type === "run.completed")).toBe(true);
  });

  it("should deny tool calls not in skill allowedTools", async () => {
    const ports = createTestPorts();
    ports.model = new ScriptedModelPort([
      { type: "tool", name: "workspace.readFile", input: { path: "/test.txt" } },
      { type: "finish" },
    ]);
    ports.skillResolver = {
      async resolve(_skillIdOrKey: string) {
        return {
          id: "skill_test" as SkillId,
          orgId: "org_test" as OrgId,
          key: "list-only",
          name: "List Only",
          instructions: "Only list files.",
          allowedTools: ["workspace.listFiles"],
          allowedSubagents: [],
          version: "1.0.0",
          status: "published",
        };
      },
      async resolveFromManifest(_manifest: AgentSkillManifest, _orgId: OrgId) {
        throw new Error("Not implemented");
      },
    };
    const engine = new NativeHarnessEngine(ports);

    const events = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Read workspace",
      skillId: "skill_test" as SkillId,
    })) {
      events.push(event);
    }

    const denied = events.filter((e) => e.type === "tool.denied");
    expect(denied.length).toBeGreaterThanOrEqual(1);
  });

  it("should expose only skill-allowed tools to the model", async () => {
    const ports = createTestPorts();
    const seenTools: string[][] = [];
    ports.skillResolver = {
      async resolve(_skillIdOrKey: string) {
        return {
          id: "skill_test" as SkillId,
          orgId: "org_test" as OrgId,
          key: "read-workspace",
          name: "Read Workspace",
          instructions: "Read workspace files only.",
          allowedTools: ["workspace.readFile"],
          allowedSubagents: [],
          version: "1.0.0",
          status: "published",
        };
      },
      async resolveFromManifest(_manifest: AgentSkillManifest, _orgId: OrgId) {
        throw new Error("Not implemented");
      },
    };
    ports.model = {
      async *start(_messages, context) {
        const tools = (context as { tools: Array<{ name: string }> }).tools;
        seenTools.push(tools.map((tool) => tool.name));
        yield { finished: true };
      },
      cancel() {},
    };
    const engine = new NativeHarnessEngine(ports);

    for await (const _event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Read a file",
      skillId: "skill_test" as SkillId,
    })) {
      // drain events
    }

    expect(seenTools).toEqual([["workspace.readFile"]]);
  });

  it("should pause and request approval when a tool call is waiting for approval", async () => {
    const ports = createTestPorts();
    ports.model = new ScriptedModelPort([
      { type: "tool", name: "workspace.writeFile", input: { path: "/out.txt", content: "hello" } },
      { type: "finish" },
    ]);
    const engine = new NativeHarnessEngine(ports);

    const events = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Write a file",
      scopes: ["workspace:write"],
    })) {
      events.push(event);
    }

    const types = events.map((e) => e.type);
    expect(types).toContain("approval.requested");
    expect(types).toContain("run.paused");
    expect(types.indexOf("approval.requested")).toBeLessThan(types.indexOf("run.paused"));
    expect(types).not.toContain("tool.started");
    expect(types).not.toContain("tool.failed");
    expect(types).not.toContain("run.completed");
  });

  it("should store pending approval before publishing run.paused", async () => {
    const ports = createTestPorts();
    ports.model = new ScriptedModelPort([
      { type: "tool", name: "workspace.writeFile", input: { path: "/out.txt", content: "hello" } },
      { type: "finish" },
    ]);
    const engine = new NativeHarnessEngine(ports);
    const resumeResults: string[][] = [];
    const originalWrite = ports.eventWriter.write.bind(ports.eventWriter);
    ports.eventWriter.write = async (input) => {
      const event = await originalWrite(input);
      if (event.type === "run.paused") {
        const events = [];
        for await (const resumed of engine.resume({
          runId: event.runId,
          approval: {
            approvalId: (event.payload as { approvalId: string }).approvalId as never,
            decision: "approved",
          },
        })) {
          events.push(resumed.type);
        }
        resumeResults.push(events);
      }
      return event;
    };

    for await (const _event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Write a file",
      scopes: ["workspace:write"],
    })) {
      // drain
    }

    expect(resumeResults[0]).toContain("approval.resolved");
    expect(resumeResults[0]).not.toContain("run.failed");
  });

  it("should resume after approval and complete the run", async () => {
    const ports = createTestPorts();
    ports.model = new ScriptedModelPort([
      { type: "tool", name: "workspace.writeFile", input: { path: "/out.txt", content: "hello" } },
      { type: "finish" },
    ]);
    const engine = new NativeHarnessEngine(ports);

    // Phase 1: run until pause
    const phase1 = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Write a file",
      scopes: ["workspace:write"],
    })) {
      phase1.push(event);
    }

    const runId = phase1[0]!.runId;
    expect(phase1.some((e) => e.type === "run.paused")).toBe(true);
    const paused = phase1.find((e) => e.type === "run.paused")!;

    // Phase 2: resume
    const phase2 = [];
    for await (const event of engine.resume({
      runId,
      approval: {
        approvalId: (paused.payload as { approvalId: string }).approvalId as never,
        decision: "approved",
      },
    })) {
      phase2.push(event.type);
    }

    expect(phase2).toContain("approval.resolved");
    expect(phase2).toContain("run.resumed");
    expect(phase2).toContain("tool.completed");
    expect(phase2).toContain("workspace.file.created");
    expect(phase2).toContain("run.completed");
  });

  it("should support rejecting a pending approval", async () => {
    const ports = createTestPorts();
    ports.model = new ScriptedModelPort([
      { type: "tool", name: "workspace.writeFile", input: { path: "/out.txt", content: "hello" } },
      { type: "finish" },
    ]);
    const engine = new NativeHarnessEngine(ports);

    const phase1 = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Write a file",
      scopes: ["workspace:write"],
    })) {
      phase1.push(event);
    }

    const paused = phase1.find((event) => event.type === "run.paused")!;
    const phase2 = [];
    for await (const event of engine.resume({
      runId: paused.runId,
      approval: {
        approvalId: (paused.payload as { approvalId: string }).approvalId as never,
        decision: "rejected",
        comment: "No write needed",
      },
    })) {
      phase2.push(event);
    }

    expect(phase2.map((event) => event.type)).toEqual([
      "approval.resolved",
      "tool.denied",
      "run.failed",
    ]);
    expect(phase2[0]!.payload).toMatchObject({ decision: "rejected" });
  });

  it("should continue model output after an approved tool", async () => {
    const ports = createTestPorts();
    ports.model = new ScriptedModelPort([
      { type: "tool", name: "workspace.writeFile", input: { path: "/out.txt", content: "hello" } },
      { type: "delta", text: "after approval" },
      { type: "finish" },
    ]);
    const engine = new NativeHarnessEngine(ports);

    const phase1 = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Write a file",
      scopes: ["workspace:write"],
    })) {
      phase1.push(event);
    }

    const paused = phase1.find((event) => event.type === "run.paused")!;
    const phase2 = [];
    for await (const event of engine.resume({
      runId: paused.runId,
      approval: {
        approvalId: (paused.payload as { approvalId: string }).approvalId as never,
        decision: "approved",
      },
    })) {
      phase2.push(event);
    }

    expect(phase2).toContainEqual(expect.objectContaining({
      type: "message.delta",
      payload: expect.objectContaining({ delta: "after approval" }),
    }));
    expect(phase2.map((event) => event.type)).toContain("run.completed");
  });

  it("should emit run.failed when skill resolution fails", async () => {
    const ports = createTestPorts();
    const engine = new NativeHarnessEngine(ports);

    const events = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Use missing skill",
      skillId: "missing_skill" as SkillId,
    })) {
      events.push(event);
    }

    expect(events.at(-1)?.type).toBe("run.failed");
    expect(events.at(-1)?.payload).toMatchObject({
      status: "failed",
      error: {
        code: "SKILL_NOT_FOUND",
      },
    });
  });

  it("should emit run.failed when model iteration throws", async () => {
    const ports = createTestPorts();
    ports.model = {
      async *start() {
        throw new Error("model stream failed");
      },
      cancel: vi.fn(),
    };
    const engine = new NativeHarnessEngine(ports);

    const events = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Fail model",
    })) {
      events.push(event);
    }

    expect(events.at(-1)?.type).toBe("run.failed");
    expect(events.at(-1)?.payload).toMatchObject({
      status: "failed",
      error: {
        code: "MODEL_FAILED",
        message: "model stream failed",
      },
    });
  });

  it("should cancel properly", async () => {
    const ports = createTestPorts();
    const engine = new NativeHarnessEngine(ports);

    await expect(engine.cancel("run_test")).resolves.toBeUndefined();
  });

  it("resume should fail for unknown run", async () => {
    const ports = createTestPorts();
    const engine = new NativeHarnessEngine(ports);

    const events = [];
    for await (const event of engine.resume({
      runId: "run_nonexistent" as unknown as RunId,
    })) {
      events.push(event);
    }

    expect(events.length).toBeGreaterThanOrEqual(1);
    expect(events[0]!.type).toBe("run.failed");
  });
});
