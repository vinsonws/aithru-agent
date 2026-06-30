import { describe, expect, it } from "vitest";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { ModelTurnLoop } from "@aithru-agent/harness";
import { TestModelAdapter } from "@aithru-agent/model";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import { SkillLoader, SkillRegistry, SkillResolver } from "@aithru-agent/skills";
import { writeFileSync, mkdirSync, rmSync } from "fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

function makeSkillDir(): string {
  const dir = join(tmpdir(), `skill_ctx_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

function setupResolver(skillContent: string, skillKey: string) {
  const root = makeSkillDir();
  try {
    mkdirSync(join(root, skillKey));
    writeFileSync(join(root, skillKey, "SKILL.md"), skillContent);
    const registry = new SkillRegistry();
    registry.loadBuiltinPackages(root);
    const store = new InMemoryStore();
    const resolver = new SkillResolver(registry, store);
    return { resolver, store, root };
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

function createRun(skillKey: string | null): AgentRun & { selected_skill_keys?: string[] | null } {
  return {
    id: `run_skill_${Date.now().toString(36)}`,
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_skill",
    task_msg: "Do the thing",
    scopes: ["*"],
    harness_options: null,
    status: "queued",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
    selected_skill_keys: skillKey ? [skillKey] : null,
  };
}

const SKILL_MD = [
  "---",
  "name: File Report",
  "description: Read workspace files and produce a report.",
  "allowed_tools:",
  "  - workspace.read_file",
  "  - workspace.list_files",
  "  - workspace.write_file",
  "denied_tools:",
  "  - workspace.delete_file",
  "---",
  "# File Report Skill",
  "",
  "Read files and write a report.",
].join("\n");

describe("ModelTurnLoop skill context", () => {
  it("injects skill instructions into model input messages", async () => {
    const { resolver, store } = setupResolver(SKILL_MD, "file-report");
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter, resolver);
    const run = createRun("file-report");
    store.createRun(run);

    let capturedMessages: any[] = [];
    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      skillResolver: resolver,
      modelAdapter: new TestModelAdapter([
        (input) => {
          capturedMessages = input.messages;
          return [{ type: "text_delta", delta: "done" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute(run);

    const systemMsg = capturedMessages.find((m) => m.role === "system");
    expect(systemMsg).toBeDefined();
    expect(systemMsg.content).toContain("Active skill: File Report");
    expect(systemMsg.content).toContain("Read files and write a report.");
  });

  it("context.packet.built contains active_skill_key but not full instructions", async () => {
    const { resolver, store } = setupResolver(SKILL_MD, "file-report");
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter, resolver);
    const run = createRun("file-report");
    store.createRun(run);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      skillResolver: resolver,
      modelAdapter: new TestModelAdapter([
        [{ type: "text_delta", delta: "done" }, { type: "completed" }],
      ]),
    });

    await loop.execute(run);

    const ctxEvents = store.listEvents(run.id).filter((e) => e.type === EVENT_TYPES.CONTEXT_PACKET_BUILT);
    expect(ctxEvents.length).toBeGreaterThanOrEqual(1);
    for (const evt of ctxEvents) {
      const stats = evt.payload as Record<string, unknown>;
      expect(stats.active_skill_key).toBe("file-report");
      expect(JSON.stringify(stats)).not.toContain("Read files and write a report.");
    }
  });

  it("emits skill.activated exactly once per run", async () => {
    const { resolver, store } = setupResolver(SKILL_MD, "file-report");
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter, resolver);
    const run = createRun("file-report");
    store.createRun(run);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      skillResolver: resolver,
      modelAdapter: new TestModelAdapter([
        [
          { type: "tool_call", id: "tc1", name: "workspace.read_file", input: { path: "/a" } },
          { type: "completed" },
        ],
        [{ type: "text_delta", delta: "done" }, { type: "completed" }],
      ]),
    });

    await loop.execute(run);

    const activated = store.listEvents(run.id).filter((e) => e.type === EVENT_TYPES.SKILL_ACTIVATED);
    expect(activated.length).toBe(1);
    const payload = activated[0].payload as Record<string, unknown>;
    expect(payload).toMatchObject({
      selected_skill_keys: ["file-report"],
      key: "file-report",
      name: "File Report",
      source: "builtin",
      trigger: "explicit",
    });
    expect(JSON.stringify(payload)).not.toContain("Read files and write a report.");
  });

  it("does not emit skill.activated when no selected_skill_keys is set", async () => {
    const { resolver, store } = setupResolver(SKILL_MD, "file-report");
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter, resolver);
    const run = createRun(null);
    store.createRun(run);

    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      skillResolver: resolver,
      modelAdapter: new TestModelAdapter([
        [{ type: "text_delta", delta: "done" }, { type: "completed" }],
      ]),
    });

    await loop.execute(run);

    const activated = store.listEvents(run.id).filter((e) => e.type === EVENT_TYPES.SKILL_ACTIVATED);
    expect(activated.length).toBe(0);
  });
});
