import { describe, expect, it } from "vitest";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { ModelTurnLoop, emitSkillActivated } from "@aithru-agent/harness";
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

function createRun(): AgentRun {
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
  it("injects active skill instructions from skill.activated events", async () => {
    const { resolver, store } = setupResolver(SKILL_MD, "file-report");
    const eventWriter = new AgentEventWriter(store);
    const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter, resolver);
    const run = createRun();
    store.createRun(run);
    emitSkillActivated({
      eventWriter,
      runId: run.id,
      threadId: run.thread_id ?? null,
      key: "file-report",
      name: "File Report",
      source: "builtin",
      version: "0.0.0",
      trigger: "explicit",
      allowedTools: ["workspace.read_file", "workspace.list_files", "workspace.write_file"],
      deniedTools: ["workspace.delete_file"],
    });

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
    expect(systemMsg.content).toContain("Active skills:");
    expect(systemMsg.content).toContain("## File Report");

    const ctxEvents = store.listEvents(run.id).filter((e) => e.type === EVENT_TYPES.CONTEXT_PACKET_BUILT);
    expect(ctxEvents.length).toBeGreaterThanOrEqual(1);
    for (const evt of ctxEvents) {
      const stats = evt.payload as Record<string, unknown>;
      expect(stats.active_skill_keys).toEqual(["file-report"]);
      expect(JSON.stringify(stats)).not.toContain("Read files and write a report.");
    }
  });
});
