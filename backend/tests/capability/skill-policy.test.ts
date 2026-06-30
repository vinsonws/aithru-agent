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

const DENY_OVERRIDE_SKILL = [
  "---",
  "name: No Delete",
  "allowed_tools:",
  "  - workspace.read_file",
  "  - workspace.list_files",
  "  - workspace.delete_file",
  "denied_tools:",
  "  - workspace.delete_file",
  "---",
  "# No Delete",
].join("\n");

describe("ProductionCapabilityRouter skill policy", () => {
  it("filters listTools by skill allowed_tools", async () => {
    const { router } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = createRun("read-only");
    const tools = await router.listTools({ run });
    const names = tools.map((t) => t.name).sort();
    expect(names).toEqual(["workspace.list_files", "workspace.read_file"]);
  });

  it("returns all tools when no selected_skill_keys is set", async () => {
    const { router } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = createRun(null);
    const tools = await router.listTools({ run });
    expect(tools.length).toBeGreaterThanOrEqual(8);
  });

  it("denies tool calls outside the skill allowlist", async () => {
    const { router, store } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = { ...createRun("read-only"), id: "run_deny_outside" };
    store.createRun(run);
    const result = await router.prepareToolCall(
      { id: "tc", name: "workspace.write_file", input: { path: "/x", content: "y" }, run_id: run.id },
      { run },
    );
    expect(result.allowed).toBe(false);
    expect(result.reason).toContain("not in skill allow list");
  });

  it("allows tool calls inside the skill allowlist", async () => {
    const { router, store } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = { ...createRun("read-only"), id: "run_allow_inside" };
    store.createRun(run);
    const result = await router.prepareToolCall(
      { id: "tc", name: "workspace.read_file", input: { path: "/x" }, run_id: run.id },
      { run },
    );
    expect(result.allowed).toBe(true);
  });

  it("denied_tools overrides allowed_tools", async () => {
    const { router, store } = setupRouter(DENY_OVERRIDE_SKILL, "no-delete");
    const run = { ...createRun("no-delete"), id: "run_deny_override" };
    store.createRun(run);

    const tools = await router.listTools({ run });
    expect(tools.map((t) => t.name)).not.toContain("workspace.delete_file");

    const result = await router.prepareToolCall(
      { id: "tc", name: "workspace.delete_file", input: { path: "/x" }, run_id: run.id },
      { run },
    );
    expect(result.allowed).toBe(false);
    expect(result.reason).toContain("denied by skill policy");
  });
});
