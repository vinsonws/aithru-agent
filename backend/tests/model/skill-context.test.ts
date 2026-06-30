import { describe, expect, it } from "vitest";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { ModelTurnLoop, emitSkillActivated } from "@aithru-agent/harness";
import { TestModelAdapter } from "@aithru-agent/model";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import { SkillRegistry, SkillResolver } from "@aithru-agent/skills";

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

describe("ModelTurnLoop skill context", () => {
  it("includes active skill instructions and visible catalog metadata without leaking inactive instructions", async () => {
    const store = new InMemoryStore();
    const registry = new SkillRegistry();
    registry.register({
      key: "file-report",
      path: "/skills/file-report",
      name: "File Report",
      description: "Read workspace files and produce a report.",
      version: "0.0.0",
      status: "published",
      enabled: true,
      allowed_tools: ["workspace.read_file", "workspace.list_files", "workspace.write_file"],
      denied_tools: ["workspace.delete_file"],
      instructions: "Read files and write a report.",
      resources: { references: [], scripts: [], assets: [], examples: [] },
    });
    registry.register({
      key: "note-taker",
      path: "/skills/note-taker",
      name: "Note Taker",
      description: "Capture concise notes.",
      version: "0.0.0",
      status: "published",
      enabled: true,
      allowed_tools: [],
      denied_tools: [],
      instructions: "Do not include this body before activation.",
      resources: { references: [], scripts: [], assets: [], examples: [] },
    });

    const resolver = new SkillResolver(registry, store);
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

    let systemMessage = "";
    let contextStats: Record<string, unknown> = {};
    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter,
      skillResolver: resolver,
      modelAdapter: new TestModelAdapter([
        (input) => {
          systemMessage = input.messages.find((message) => message.role === "system")?.content ?? "";
          contextStats = input.context;
          return [{ type: "text_delta", delta: "done" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute(run);

    expect(systemMessage).toContain("Active skills:");
    expect(systemMessage).toContain("## File Report");
    expect(systemMessage).toContain("Available skills:");
    expect(systemMessage).toContain("- file-report: File Report — Read workspace files and produce a report.");
    expect(systemMessage).toContain("- note-taker: Note Taker — Capture concise notes.");
    expect(systemMessage).not.toContain("Do not include this body before activation.");
    expect(contextStats.active_skill_keys).toEqual(["file-report"]);
    expect(contextStats.visible_skill_count).toBe(2);
    expect(JSON.stringify(contextStats)).not.toContain("Read files and write a report.");
    expect(JSON.stringify(contextStats)).not.toContain("Do not include this body before activation.");

    const ctxEvents = store.listEvents(run.id).filter((event) => event.type === EVENT_TYPES.CONTEXT_PACKET_BUILT);
    expect(ctxEvents.length).toBeGreaterThanOrEqual(1);
  });
});
