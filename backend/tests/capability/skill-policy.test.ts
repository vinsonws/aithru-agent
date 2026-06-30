import { describe, it, expect } from "vitest";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter } from "@aithru-agent/stream";
import { SkillLoader, SkillRegistry, SkillResolver } from "@aithru-agent/skills";
import { writeFileSync, mkdirSync, rmSync } from "fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

function makeSkillDir(): string {
  const dir = join(tmpdir(), `cap_skill_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

function setupRouter(skillMd: string, skillKey: string) {
  const root = makeSkillDir();
  mkdirSync(join(root, skillKey));
  writeFileSync(join(root, skillKey, "SKILL.md"), skillMd);
  const registry = new SkillRegistry();
  registry.loadBuiltinPackages(root);
  rmSync(root, { recursive: true, force: true });
  const store = new InMemoryStore();
  const eventWriter = new AgentEventWriter(store);
  const resolver = new SkillResolver(registry, store);
  const router = new ProductionCapabilityRouter(store, eventWriter, resolver);
  return { router, store };
}

function createRun(skillKey: string | null): AgentRun & { selected_skill_keys?: string[] | null } {
  return {
    id: "run_cap_skill",
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "api",
    thread_id: null,
    workspace_id: "ws_cap",
    task_msg: "test",
    scopes: ["*"],
    harness_options: null,
    status: "running",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    current_approval_id: null,
    claim: null,
    result: null,
    error: null,
    selected_skill_keys: skillKey ? [skillKey] : null,
  };
}

const ALLOWED_SKILL = [
  "---",
  "name: Read Only",
  "allowed_tools:",
  "  - workspace.read_file",
  "  - workspace.list_files",
  "---",
  "# Read Only",
].join("\n");

describe("ProductionCapabilityRouter skill policy", () => {
  it("does not filter listTools from run.selected_skill_keys", async () => {
    const { router } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = createRun("read-only");
    const tools = await router.listTools({ run });
    expect(tools.length).toBeGreaterThanOrEqual(8);
  });

  it("still returns all tools when no selected_skill_keys is set", async () => {
    const { router } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = createRun(null);
    const tools = await router.listTools({ run });
    expect(tools.length).toBeGreaterThanOrEqual(8);
  });

  it("does not deny tool calls from run.selected_skill_keys", async () => {
    const { router, store } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = { ...createRun("read-only"), id: "run_no_skill_policy" };
    store.createRun(run);
    const result = await router.prepareToolCall(
      { id: "tc", name: "workspace.write_file", input: { path: "/x", content: "y" }, run_id: run.id },
      { run },
    );
    expect(result.allowed).toBe(true);
    expect(result.reason).toBeUndefined();
  });

  it("still enforces ordinary scope checks", async () => {
    const { router, store } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = {
      ...createRun("read-only"),
      id: "run_scope_denied",
      scopes: ["workspace:read"],
    };
    store.createRun(run);
    const result = await router.prepareToolCall(
      { id: "tc", name: "workspace.write_file", input: { path: "/x", content: "y" }, run_id: run.id },
      { run },
    );
    expect(result.allowed).toBe(false);
    expect(result.reason).toContain("Missing scopes");
  });
});
