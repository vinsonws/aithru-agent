import Fastify, { type FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createRuntime, getRuntime, resetRuntimeForTests } from "../../apps/api/src/runtime.js";
import { registerApprovalRoutes } from "../../apps/api/src/routes/approvals.js";
import { registerCompatRoutes } from "../../apps/api/src/routes/compat.js";
import { registerRunRoutes } from "../../apps/api/src/routes/runs.js";
import type { AgentRun } from "@aithru-agent/contracts";

const actor = {
  actorType: "user" as const,
  userId: "user_1",
  orgId: "org_1",
  scopes: ["agent.app.runs.read", "agent.app.runs.execute", "agent.app.runs.cancel", "agent.app.approvals.resolve"],
  roles: [],
  tokenType: "hosted_access" as const,
  claims: {},
};

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function run(id: string, actor_user_id = "user_2"): AgentRun {
  return {
    id,
    org_id: "org_1",
    actor_user_id,
    source: "chat",
    thread_id: "thread_foreign",
    workspace_id: "ws_thread_thread_foreign",
    task_msg: "foreign run",
    scopes: ["*"],
    harness_options: null,
    status: "queued",
    current_approval_id: null,
    started_at: now(),
    completed_at: null,
    claim: null,
    result: null,
    error: null,
  };
}

async function appWithActor(register: (app: FastifyInstance) => void): Promise<FastifyInstance> {
  resetRuntimeForTests();
  await createRuntime();
  const app = Fastify({ logger: false });
  app.addHook("preHandler", async (request) => {
    (request as any).aithruActor = actor;
  });
  register(app);
  await app.ready();
  return app;
}

describe("authenticated route resource access", () => {
  let app: FastifyInstance | null = null;

  beforeEach(() => {
    resetRuntimeForTests();
  });

  afterEach(async () => {
    await app?.close();
    resetRuntimeForTests();
    app = null;
  });

  it("rejects creating a run attached to another user's thread before mutating state", async () => {
    app = await appWithActor(registerRunRoutes);
    getRuntime().store.createThread({
      id: "thread_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      title: "Foreign",
      status: "active",
      created_at: now(),
      updated_at: now(),
    });

    const response = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "spoofed_org",
        actor_user_id: "spoofed_user",
        thread_id: "thread_foreign",
        task_msg: "write into foreign thread",
        persist_task_msg_message: true,
      },
    });

    expect(response.statusCode).toBe(403);
    expect(getRuntime().store.listRuns({ thread_id: "thread_foreign" })).toEqual([]);
    expect(getRuntime().store.listMessages("thread_foreign")).toEqual([]);
  });

  it("rejects compat reads, streams, and cancels for another user's run", async () => {
    app = await appWithActor(registerCompatRoutes);
    getRuntime().store.createThread({
      id: "thread_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      title: "Foreign",
      status: "active",
      created_at: now(),
      updated_at: now(),
    });
    getRuntime().store.createRun(run("run_foreign"));

    const thread = await app.inject({ method: "GET", url: "/api/threads/thread_foreign" });
    const stream = await app.inject({ method: "GET", url: "/api/threads/thread_foreign/runs/run_foreign/stream" });
    const cancel = await app.inject({ method: "POST", url: "/api/threads/thread_foreign/runs/run_foreign/cancel" });

    expect(thread.statusCode).toBe(403);
    expect(stream.statusCode).toBe(403);
    expect(cancel.statusCode).toBe(403);
    expect(getRuntime().store.getRun("run_foreign")?.status).toBe("queued");
  });

  it("scopes runtime cancellation by org", async () => {
    await createRuntime();
    const runtime = getRuntime();
    runtime.store.createRun(run("run_runtime_cancel", "user_1"));

    expect(runtime.cancelRun("run_runtime_cancel", "org_2")).toBeUndefined();
    expect(runtime.store.getRun("run_runtime_cancel")?.status).toBe("queued");
    expect(runtime.cancelRun("run_runtime_cancel", "org_1")?.status).toBe("cancelled");
  });

  it("rejects resolving another user's approval before changing approval status", async () => {
    app = await appWithActor(registerApprovalRoutes);
    getRuntime().store.createRun(run("run_approval"));
    getRuntime().store.createApproval({
      id: "approval_foreign",
      run_id: "run_approval",
      tool_call_id: "tc_foreign",
      tool_name: "workspace.write_file",
      status: "pending",
      created_at: now(),
    });

    const response = await app.inject({
      method: "POST",
      url: "/api/approvals/approval_foreign/resolve",
      payload: { decision: "approved" },
    });

    expect(response.statusCode).toBe(403);
    expect(getRuntime().store.getApproval("approval_foreign")?.status).toBe("pending");
  });

  it("rejects compat document mutations for resources owned by another user in the same org", async () => {
    app = await appWithActor(registerCompatRoutes);
    const timestamp = now();
    const store = getRuntime().store;
    store.upsertDocument("model_profile_entry", "profile_foreign", {
      id: "profile_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      key: "foreign-profile",
      provider: "test",
      model: "test",
      enabled: true,
      auth_secret: { has_secret: false, secret_ref: null, redacted: true },
      created_at: timestamp,
      updated_at: timestamp,
    });
    store.upsertDocument("skill_registry_entry", "skill_foreign", {
      id: "skill_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      key: "foreign-skill",
      name: "Foreign Skill",
      description: null,
      version: "1.0.0",
      status: "published",
      enabled: true,
      configuration: { instructions: "private", allowed_tools: [], denied_tools: [] },
      created_at: timestamp,
      updated_at: timestamp,
    });
    store.upsertDocument("external_tool_config_entry", "external_foreign", {
      id: "external_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      key: "foreign-tool",
      name: "Foreign Tool",
      provider_kind: "mcp",
      enabled: true,
      created_at: timestamp,
      updated_at: timestamp,
    });
    store.upsertDocument("subagent_spec", "subagent_foreign", {
      id: "subagent_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      key: "foreign-subagent",
      name: "Foreign Subagent",
      instructions: "private",
      created_at: timestamp,
      updated_at: timestamp,
    });
    store.upsertDocument("memory", "memory_foreign", {
      id: "memory_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      key: "foreign-memory",
      value: "private",
      created_at: timestamp,
      updated_at: timestamp,
    });

    const profile = await app.inject({
      method: "PATCH",
      url: "/api/model-profiles/foreign-profile",
      payload: { enabled: false },
    });
    const skill = await app.inject({
      method: "PATCH",
      url: "/api/skill-registry/foreign-skill",
      payload: { enabled: false },
    });
    const external = await app.inject({
      method: "PATCH",
      url: "/api/external-tools/configs/foreign-tool",
      payload: { enabled: false },
    });
    const subagent = await app.inject({
      method: "GET",
      url: "/api/subagents/foreign-subagent",
    });
    const memoryDelete = await app.inject({
      method: "DELETE",
      url: "/api/memory/memory_foreign",
    });

    expect(profile.statusCode).toBe(403);
    expect(skill.statusCode).toBe(403);
    expect(external.statusCode).toBe(403);
    expect(subagent.statusCode).toBe(404);
    expect(JSON.parse(memoryDelete.body)).toMatchObject({ forgotten: false, deleted_count: 0 });
    expect(store.getDocument("model_profile_entry", "profile_foreign")?.payload).toMatchObject({ enabled: true });
    expect(store.getDocument("skill_registry_entry", "skill_foreign")?.payload).toMatchObject({ enabled: true });
    expect(store.getDocument("external_tool_config_entry", "external_foreign")?.payload).toMatchObject({ enabled: true });
    expect(store.getDocument("memory", "memory_foreign")).toBeDefined();
  });

  it("uses the current user's skill registry entry when another user has the same key", async () => {
    app = await appWithActor(registerCompatRoutes);
    const timestamp = now();
    const store = getRuntime().store;
    store.upsertDocument("skill_registry_entry", "a_foreign_shared_skill", {
      id: "a_foreign_shared_skill",
      org_id: "org_1",
      owner_user_id: "user_2",
      key: "shared-skill",
      name: "Foreign Shared Skill",
      version: "1.0.0",
      status: "published",
      enabled: true,
      configuration: { instructions: "foreign", allowed_tools: [], denied_tools: [] },
      created_at: timestamp,
      updated_at: timestamp,
    });
    store.upsertDocument("skill_registry_entry", "z_own_shared_skill", {
      id: "z_own_shared_skill",
      org_id: "org_1",
      owner_user_id: "user_1",
      key: "shared-skill",
      name: "Own Shared Skill",
      version: "1.0.0",
      status: "published",
      enabled: true,
      configuration: { instructions: "own", allowed_tools: [], denied_tools: [] },
      created_at: timestamp,
      updated_at: timestamp,
    });

    const read = await app.inject({
      method: "GET",
      url: "/api/skill-registry/shared-skill",
    });
    const patch = await app.inject({
      method: "PATCH",
      url: "/api/skill-registry/shared-skill",
      payload: { enabled: false },
    });

    expect(JSON.parse(read.body)).toMatchObject({ id: "z_own_shared_skill", owner_user_id: "user_1" });
    expect(patch.statusCode).toBe(200);
    expect(store.getDocument("skill_registry_entry", "z_own_shared_skill")?.payload).toMatchObject({ enabled: false });
    expect(store.getDocument("skill_registry_entry", "a_foreign_shared_skill")?.payload).toMatchObject({ enabled: true });
  });
});
