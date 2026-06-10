import { describe, it, expect } from "vitest";
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

function createTestPorts(): AgentHarnessEnginePorts {
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
    expect(types).toContain("tool.started");
    expect(types).toContain("approval.requested");
    expect(types).toContain("run.paused");
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
    expect(types).not.toContain("tool.failed");
    expect(types).not.toContain("run.completed");
  });

  it("should resume after approval and complete the run", async () => {
    const ports = createTestPorts();
    ports.model = new ScriptedModelPort([
      { type: "tool", name: "workspace.writeFile", input: { path: "/out.txt", content: "hello" } },
      { type: "finish" },
    ]);
    const engine = new NativeHarnessEngine(ports);

    // Phase 1: run until pause
    const phase1: Array<{ type: string; runId: RunId }> = [];
    for await (const event of engine.run({
      orgId: "org_test" as OrgId,
      actorUserId: "user_test" as UserId,
      goal: "Write a file",
      scopes: ["workspace:write"],
    })) {
      phase1.push({ type: event.type, runId: event.runId });
    }

    const runId = phase1[0]!.runId;
    expect(phase1.some((e) => e.type === "run.paused")).toBe(true);

    // Phase 2: resume
    const phase2 = [];
    for await (const event of engine.resume({ runId })) {
      phase2.push(event.type);
    }

    expect(phase2).toContain("approval.resolved");
    expect(phase2).toContain("run.resumed");
    expect(phase2).toContain("tool.completed");
    expect(phase2).toContain("workspace.file.created");
    expect(phase2).toContain("run.completed");
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
