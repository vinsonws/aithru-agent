import { describe, it, expect } from "vitest";
import { ProductionCapabilityRouter, resolveSkillPolicy } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES, VISIBILITY } from "@aithru-agent/stream";
import { SkillRegistry, SkillResolver } from "@aithru-agent/skills";
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
  return { router, store, eventWriter };
}

function createRun(): AgentRun {
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
  };
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

const ALLOWED_SKILL = [
  "---",
  "name: Read Only",
  "allowed_tools:",
  "  - workspace.read_file",
  "  - workspace.list_files",
  "---",
  "# Read Only",
].join("\n");

const WRITE_SKILL = [
  "---",
  "name: Write Only",
  "allowed_tools:",
  "  - workspace.write_file",
  "---",
  "# Write Only",
].join("\n");

describe("ProductionCapabilityRouter skill policy", () => {
  it("intersects allowlists and unions denylists across loaded skills", () => {
    const policy = resolveSkillPolicy([
      { allowed_tools: ["workspace.list_files", "workspace.read_file"], denied_tools: ["workspace.delete_file"] },
      { allowed_tools: ["workspace.read_file", "workspace.write_file"], denied_tools: ["workspace.write_file"] },
    ]);

    expect([...policy.allowedTools]).toEqual(["workspace.read_file"]);
    expect([...policy.deniedTools].sort()).toEqual(["workspace.delete_file", "workspace.write_file"]);
  });

  it("filters listTools from active skill events", async () => {
    const { router, eventWriter, store } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = createRun();
    store.createRun(run);
    activateSkills(eventWriter, run, [{ key: "read-only", allowed_tools: ["workspace.read_file", "workspace.list_files"] }]);
    const tools = await router.listTools({ run });
    expect(tools.map((tool) => tool.name)).toEqual([
      "workspace.list_files",
      "workspace.read_file",
    ]);
  });

  it("still returns all tools when no active skills are set", async () => {
    const { router } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = createRun();
    const tools = await router.listTools({ run });
    expect(tools.length).toBeGreaterThanOrEqual(8);
  });

  it("denies tool calls from active skill events", async () => {
    const { router, store, eventWriter } = setupRouter(ALLOWED_SKILL, "read-only");
    const run = { ...createRun(), id: "run_active_skill_policy" };
    store.createRun(run);
    activateSkills(eventWriter, run, [{ key: "read-only", allowed_tools: ["workspace.read_file", "workspace.list_files"] }]);
    const result = await router.prepareToolCall(
      { id: "tc", name: "workspace.write_file", input: { path: "/x", content: "y" }, run_id: run.id },
      { run },
    );
    expect(result.allowed).toBe(false);
    expect(result.reason).toContain('not in skill allow list');
  });

  it("still enforces ordinary scope checks", async () => {
    const { router, store, eventWriter } = setupRouter(WRITE_SKILL, "write-only");
    const run = {
      ...createRun(),
      id: "run_scope_denied",
      scopes: ["workspace:read"],
    };
    store.createRun(run);
    activateSkills(eventWriter, run, [{ key: "write-only", allowed_tools: ["workspace.write_file"] }]);
    const result = await router.prepareToolCall(
      { id: "tc", name: "workspace.write_file", input: { path: "/x", content: "y" }, run_id: run.id },
      { run },
    );
    expect(result.allowed).toBe(false);
    expect(result.reason).toContain("Missing scopes");
  });

  it("keeps enforcing the activation snapshot after resolver state disappears", async () => {
    const store = new InMemoryStore();
    const eventWriter = new AgentEventWriter(store);
    const router = new ProductionCapabilityRouter(store, eventWriter);
    const run = { ...createRun(), id: "run_event_snapshot_policy" };
    store.createRun(run);
    activateSkills(eventWriter, run, [{
      key: "read-only",
      allowed_tools: ["workspace.read_file", "workspace.list_files"],
      denied_tools: ["workspace.delete_file"],
    }]);

    const tools = await router.listTools({ run });
    expect(tools.map((tool) => tool.name)).toEqual([
      "workspace.list_files",
      "workspace.read_file",
    ]);

    const denied = await router.prepareToolCall(
      { id: "tc", name: "workspace.write_file", input: { path: "/x", content: "y" }, run_id: run.id },
      { run },
    );
    expect(denied.allowed).toBe(false);
    expect(denied.reason).toContain('not in skill allow list');
  });
});
