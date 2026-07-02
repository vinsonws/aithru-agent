import Fastify, { type FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createRuntime, getRuntime, resetRuntimeForTests } from "../../apps/api/src/runtime.js";
import { registerApprovalRoutes } from "../../apps/api/src/routes/approvals.js";
import { registerCompatRoutes } from "../../apps/api/src/routes/compat.js";
import { registerModelConfigRoutes } from "../../apps/api/src/routes/model-config.js";
import { registerRunRoutes } from "../../apps/api/src/routes/runs.js";
import type { AgentRun } from "@aithru-agent/contracts";

const actor = {
  actorType: "user" as const,
  userId: "user_1",
  orgId: "org_1",
  scopes: [
    "agent.app.runs.read",
    "agent.app.runs.execute",
    "agent.app.runs.cancel",
    "agent.app.approvals.resolve",
    "agent.app.workspaces.read",
    "agent.app.workspaces.write",
  ],
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

type TestActor = typeof actor;

async function appWithActor(register: (app: FastifyInstance) => void, currentActor: TestActor = actor): Promise<FastifyInstance> {
  resetRuntimeForTests();
  await createRuntime();
  const app = Fastify({ logger: false });
  app.addHook("preHandler", async (request) => {
    (request as any).aithruActor = currentActor;
  });
  register(app);
  await app.ready();
  return app;
}

async function appWithSwitchableActor(register: (app: FastifyInstance) => void, initialActor: TestActor = actor) {
  resetRuntimeForTests();
  await createRuntime();
  let currentActor = initialActor;
  const app = Fastify({ logger: false });
  app.addHook("preHandler", async (request) => {
    (request as any).aithruActor = currentActor;
  });
  register(app);
  await app.ready();
  return {
    app,
    setActor(nextActor: TestActor) {
      currentActor = nextActor;
    },
  };
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

  it("rejects direct workspace file access for another user's workspace", async () => {
    app = await appWithActor(registerCompatRoutes);
    const store = getRuntime().store;
    store.createThread({
      id: "thread_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      title: "Foreign",
      status: "active",
      created_at: now(),
      updated_at: now(),
    });
    store.createRun(run("run_foreign"));
    store.writeFile("ws_thread_thread_foreign", "/secret.txt", "private");

    const list = await app.inject({ method: "GET", url: "/api/workspaces/ws_thread_thread_foreign/files" });
    const read = await app.inject({ method: "GET", url: "/api/workspaces/ws_thread_thread_foreign/files/secret.txt" });
    const write = await app.inject({
      method: "PUT",
      url: "/api/workspaces/ws_thread_thread_foreign/files/secret.txt",
      payload: { content: "changed" },
    });
    const remove = await app.inject({ method: "DELETE", url: "/api/workspaces/ws_thread_thread_foreign/files/secret.txt" });

    expect(list.statusCode).toBe(403);
    expect(read.statusCode).toBe(403);
    expect(write.statusCode).toBe(403);
    expect(remove.statusCode).toBe(403);
    expect(store.readFile("ws_thread_thread_foreign", "/secret.txt")?.content).toBe("private");
  });

  it("rejects authenticated writes to unbound workspace ids", async () => {
    app = await appWithActor(registerCompatRoutes);
    const store = getRuntime().store;
    store.writeFile("ws_legacy_unbound", "/secret.txt", "private");

    const write = await app.inject({
      method: "PUT",
      url: "/api/workspaces/ws_legacy_unbound/files/secret.txt",
      payload: { content: "changed" },
    });

    expect(write.statusCode).toBe(403);
    expect(store.readFile("ws_legacy_unbound", "/secret.txt")?.content).toBe("private");
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

  it("migrates only the current user's legacy model profiles when listing model providers", async () => {
    app = await appWithActor(registerModelConfigRoutes);
    const timestamp = now();
    const store = getRuntime().store;
    store.upsertDocument("model_profile_entry", "profile_own", {
      id: "profile_own",
      org_id: "org_1",
      owner_user_id: "user_1",
      key: "own-profile",
      name: "Own Profile",
      provider: "test",
      model: "test:echo",
      enabled: true,
      auth_secret: { has_secret: false, secret_ref: null, redacted: true },
      metadata: null,
      created_at: timestamp,
      updated_at: timestamp,
    });
    store.upsertDocument("model_profile_entry", "profile_foreign_migrate", {
      id: "profile_foreign_migrate",
      org_id: "org_1",
      owner_user_id: "user_2",
      key: "foreign-profile",
      name: "Foreign Profile",
      provider: "test",
      model: "test:echo",
      enabled: true,
      auth_secret: { has_secret: false, secret_ref: null, redacted: true },
      metadata: null,
      created_at: timestamp,
      updated_at: timestamp,
    });

    const response = await app.inject({ method: "GET", url: "/api/model-providers" });

    expect(response.statusCode).toBe(200);
    expect(JSON.parse(response.body)).toEqual([
      expect.objectContaining({
        owner_user_id: "user_1",
        key: "test",
        models: [expect.objectContaining({ key: "echo", owner_user_id: "user_1" })],
      }),
    ]);
    expect(
      store.listDocuments("model_provider_entry", "org_1").filter((doc) => (doc.payload as any).owner_user_id === "user_2"),
    ).toHaveLength(0);
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

  it("allows same-org users to create same-key owned compat resources independently", async () => {
    const user2: TestActor = { ...actor, userId: "user_2" };
    const switchable = await appWithSwitchableActor(registerCompatRoutes);
    app = switchable.app;

    const firstProfile = await app.inject({
      method: "POST",
      url: "/api/model-profiles",
      payload: { key: "shared-profile", provider: "test", model: "one" },
    });
    const firstSkill = await app.inject({
      method: "POST",
      url: "/api/skill-registry",
      payload: { key: "same-skill", name: "One" },
    });
    const firstExternal = await app.inject({
      method: "POST",
      url: "/api/external-tools/configs",
      payload: { key: "same-tool", provider_kind: "mcp", name: "One" },
    });

    switchable.setActor(user2);
    const secondProfile = await app.inject({
      method: "POST",
      url: "/api/model-profiles",
      payload: { key: "shared-profile", provider: "test", model: "two" },
    });
    const secondSkill = await app.inject({
      method: "POST",
      url: "/api/skill-registry",
      payload: { key: "same-skill", name: "Two" },
    });
    const secondExternal = await app.inject({
      method: "POST",
      url: "/api/external-tools/configs",
      payload: { key: "same-tool", provider_kind: "mcp", name: "Two" },
    });

    expect(firstProfile.statusCode).toBe(201);
    expect(firstSkill.statusCode).toBe(201);
    expect(firstExternal.statusCode).toBe(201);
    expect(secondProfile.statusCode).toBe(201);
    expect(secondSkill.statusCode).toBe(201);
    expect(secondExternal.statusCode).toBe(201);
    expect(JSON.parse(secondProfile.body)).toMatchObject({ key: "shared-profile", owner_user_id: "user_2", model: "two" });
    expect(JSON.parse(secondSkill.body)).toMatchObject({ key: "same-skill", owner_user_id: "user_2", name: "Two" });
    expect(JSON.parse(secondExternal.body)).toMatchObject({ key: "same-tool", owner_user_id: "user_2", name: "Two" });
  });

  it("rejects duplicate same-owner compat resource creates when legacy ids differ", async () => {
    app = await appWithActor(registerCompatRoutes);
    const store = getRuntime().store;
    store.upsertDocument("model_profile_entry", "legacy_profile_id", {
      id: "legacy_profile_id",
      org_id: actor.orgId,
      owner_user_id: actor.userId,
      key: "legacy-profile",
    });
    store.upsertDocument("skill_registry_entry", "legacy_skill_id", {
      id: "legacy_skill_id",
      org_id: actor.orgId,
      owner_user_id: actor.userId,
      key: "legacy-skill",
    });
    store.upsertDocument("external_tool_config_entry", "legacy_external_id", {
      id: "legacy_external_id",
      org_id: actor.orgId,
      owner_user_id: actor.userId,
      key: "legacy-tool",
    });

    const profile = await app.inject({
      method: "POST",
      url: "/api/model-profiles",
      payload: { key: "legacy-profile", provider: "test", model: "next" },
    });
    const skill = await app.inject({
      method: "POST",
      url: "/api/skill-registry",
      payload: { key: "legacy-skill", name: "Next" },
    });
    const external = await app.inject({
      method: "POST",
      url: "/api/external-tools/configs",
      payload: { key: "legacy-tool", provider_kind: "mcp", name: "Next" },
    });

    expect(profile.statusCode).toBe(409);
    expect(skill.statusCode).toBe(409);
    expect(external.statusCode).toBe(409);
    expect(store.listDocuments("model_profile_entry", actor.orgId).filter((doc) => (doc.payload as any).key === "legacy-profile")).toHaveLength(1);
    expect(store.listDocuments("skill_registry_entry", actor.orgId).filter((doc) => (doc.payload as any).key === "legacy-skill")).toHaveLength(1);
    expect(store.listDocuments("external_tool_config_entry", actor.orgId).filter((doc) => (doc.payload as any).key === "legacy-tool")).toHaveLength(1);
  });

  it("returns tenant-local builtin compat resources for non-default orgs", async () => {
    app = await appWithActor(registerCompatRoutes, { ...actor, orgId: "org_2" });

    const profiles = await app.inject({ method: "GET", url: "/api/model-profiles" });
    const skills = await app.inject({ method: "GET", url: "/api/skill-registry" });
    const external = await app.inject({ method: "GET", url: "/api/external-tools/configs" });

    expect(JSON.parse(profiles.body)[0]).toMatchObject({ org_id: "org_2" });
    expect(JSON.parse(skills.body).every((entry: any) => entry.org_id === "org_2")).toBe(true);
    expect(JSON.parse(external.body)[0]).toMatchObject({ org_id: "org_2" });
  });

  it("returns an empty model on the builtin default model profile", async () => {
    app = await appWithActor(registerCompatRoutes);

    const profiles = await app.inject({ method: "GET", url: "/api/model-profiles" });

    expect(JSON.parse(profiles.body)[0]).toMatchObject({ key: "default", model: "" });
  });
});
