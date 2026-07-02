import Fastify, { type FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createRuntime, getRuntime, resetRuntimeForTests } from "../../apps/api/src/runtime.js";
import { registerModelConfigRoutes } from "../../apps/api/src/routes/model-config.js";

const actor = {
  actorType: "user" as const,
  userId: "user_1",
  orgId: "org_1",
  scopes: ["agent.app.settings.write", "agent.app.settings.read"],
  roles: [],
  tokenType: "hosted_access" as const,
  claims: {},
};

async function appWithActor(currentActor = actor): Promise<FastifyInstance> {
  resetRuntimeForTests();
  await createRuntime();
  const app = Fastify({ logger: false });
  app.addHook("preHandler", async (request) => {
    (request as any).aithruActor = currentActor;
  });
  registerModelConfigRoutes(app);
  await app.ready();
  return app;
}

async function appWithoutActor(): Promise<FastifyInstance> {
  resetRuntimeForTests();
  await createRuntime();
  const app = Fastify({ logger: false });
  registerModelConfigRoutes(app);
  await app.ready();
  return app;
}

async function appWithSwitchableActor(initialActor = actor) {
  resetRuntimeForTests();
  await createRuntime();
  let currentActor = initialActor;
  const app = Fastify({ logger: false });
  app.addHook("preHandler", async (request) => {
    (request as any).aithruActor = currentActor;
  });
  registerModelConfigRoutes(app);
  await app.ready();
  return {
    app,
    setActor(nextActor: typeof actor) {
      currentActor = nextActor;
    },
  };
}

describe("model provider routes", () => {
  let app: FastifyInstance | null = null;

  beforeEach(() => resetRuntimeForTests());
  afterEach(async () => {
    await app?.close();
    resetRuntimeForTests();
  });

  it("creates a provider with a redacted provider secret and multiple models", async () => {
    app = await appWithActor();
    const provider = await app.inject({
      method: "POST",
      url: "/api/model-providers",
      payload: {
        key: "deepseek",
        name: "DeepSeek",
        kind: "openai_compatible",
        base_url: "https://api.deepseek.com",
        compat: "deepseek",
        auth_secret: { write_only_value: "sk-test" },
      },
    });
    expect(provider.statusCode).toBe(201);
    expect(provider.body).not.toContain("sk-test");
    expect(JSON.parse(provider.body).auth_secret).toMatchObject({ has_secret: true, redacted: true });

    const flash = await app.inject({
      method: "POST",
      url: "/api/model-providers/deepseek/models",
      payload: {
        key: "deepseek-v4-flash",
        name: "DeepSeek V4 Flash",
        provider_model_id: "deepseek-v4-flash",
        capabilities: { vision: false, thinking: true },
      },
    });
    expect(flash.statusCode).toBe(201);

    const pro = await app.inject({
      method: "POST",
      url: "/api/model-providers/deepseek/models",
      payload: {
        key: "deepseek-v4-pro",
        name: "DeepSeek V4 Pro",
        provider_model_id: "deepseek-v4-pro",
        capabilities: { vision: false, thinking: true },
      },
    });
    expect(pro.statusCode).toBe(201);

    const list = await app.inject({ method: "GET", url: "/api/model-providers" });
    expect(JSON.parse(list.body)[0].models.map((model: any) => model.key)).toEqual([
      "deepseek-v4-flash",
      "deepseek-v4-pro",
    ]);
  });

  it("does not expose providers owned by another user in the same org", async () => {
    app = await appWithActor();
    getRuntime().store.upsertDocument("model_provider_entry", "provider_foreign", {
      id: "provider_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      key: "foreign",
      name: "Foreign",
      kind: "openai_compatible",
      enabled: true,
      base_url: "https://example.invalid/v1",
      compat: null,
      auth_secret: null,
      metadata: null,
      created_at: "2026-07-02T00:00:00Z",
      updated_at: "2026-07-02T00:00:00Z",
    });

    const res = await app.inject({ method: "GET", url: "/api/model-providers/foreign" });
    expect(res.statusCode).toBe(404);
  });

  it("rejects caller supplied provider secret refs", async () => {
    const switchable = await appWithSwitchableActor();
    app = switchable.app;

    const created = await app.inject({
      method: "POST",
      url: "/api/model-providers",
      payload: {
        key: "deepseek",
        name: "DeepSeek",
        kind: "openai_compatible",
        auth_secret: { write_only_value: "sk-user-1" },
      },
    });
    expect(created.statusCode).toBe(201);
    const secretRef = JSON.parse(created.body).auth_secret.secret_ref;

    switchable.setActor({ ...actor, userId: "user_2" });
    const copiedOnCreate = await app.inject({
      method: "POST",
      url: "/api/model-providers",
      payload: {
        key: "copied",
        name: "Copied",
        kind: "openai_compatible",
        auth_secret: { secret_ref: secretRef },
      },
    });
    expect(copiedOnCreate.statusCode).toBe(400);

    const safe = await app.inject({
      method: "POST",
      url: "/api/model-providers",
      payload: { key: "safe", name: "Safe", kind: "openai_compatible" },
    });
    expect(safe.statusCode).toBe(201);

    const copiedOnPatch = await app.inject({
      method: "PATCH",
      url: "/api/model-providers/safe",
      payload: { auth_secret: { secret_ref: secretRef } },
    });
    expect(copiedOnPatch.statusCode).toBe(400);

    const safeAfterPatch = await app.inject({
      method: "GET",
      url: "/api/model-providers/safe",
    });
    expect(JSON.parse(safeAfterPatch.body).auth_secret).toEqual({
      has_secret: false,
      secret_ref: null,
      redacted: true,
    });
  });

  it("clears the owner's default when deleting the default model", async () => {
    app = await appWithActor();
    await app.inject({
      method: "POST",
      url: "/api/model-providers",
      payload: { key: "test", name: "Test", kind: "test", enabled: true },
    });
    await app.inject({
      method: "POST",
      url: "/api/model-providers/test/models",
      payload: { key: "echo", name: "Echo", provider_model_id: "test", enabled: true },
    });
    getRuntime().store.setSetting("org_1", "model.default_ref.user_1", "test/echo");

    const deleted = await app.inject({
      method: "DELETE",
      url: "/api/model-providers/test/models/echo",
    });
    expect(deleted.statusCode).toBe(200);
    expect(getRuntime().store.getSetting("org_1", "model.default_ref.user_1")).toBe("");
  });

  it("sets and clears the explicit default model", async () => {
    app = await appWithActor();
    await app.inject({
      method: "POST",
      url: "/api/model-providers",
      payload: { key: "test", name: "Test", kind: "test", enabled: true },
    });
    await app.inject({
      method: "POST",
      url: "/api/model-providers/test/models",
      payload: { key: "echo", name: "Echo", provider_model_id: "test", enabled: true },
    });

    const set = await app.inject({
      method: "PUT",
      url: "/api/model-default",
      payload: { model_ref: "test/echo" },
    });
    expect(set.statusCode).toBe(200);
    expect(JSON.parse(set.body)).toEqual({ model_ref: "test/echo" });

    const read = await app.inject({ method: "GET", url: "/api/model-default" });
    expect(JSON.parse(read.body)).toEqual({ model_ref: "test/echo" });

    const cleared = await app.inject({
      method: "PUT",
      url: "/api/model-default",
      payload: { model_ref: null },
    });
    expect(cleared.statusCode).toBe(200);
    expect(JSON.parse(cleared.body)).toEqual({ model_ref: null });
  });

  it("does not clear another owner's default when same-named model is deleted", async () => {
    const secondActor = { ...actor, userId: "user_2" };
    const switchable = await appWithSwitchableActor();
    app = switchable.app;

    await app.inject({
      method: "POST",
      url: "/api/model-providers",
      payload: { key: "shared", name: "Shared", kind: "test", enabled: true },
    });
    await app.inject({
      method: "POST",
      url: "/api/model-providers/shared/models",
      payload: { key: "echo", name: "Echo", provider_model_id: "shared-echo", enabled: true },
    });
    await app.inject({
      method: "PUT",
      url: "/api/model-default",
      payload: { model_ref: "shared/echo" },
    });

    switchable.setActor(secondActor);
    await app.inject({
      method: "POST",
      url: "/api/model-providers",
      payload: { key: "shared", name: "Shared", kind: "test", enabled: true },
    });
    await app.inject({
      method: "POST",
      url: "/api/model-providers/shared/models",
      payload: { key: "echo", name: "Echo", provider_model_id: "shared-echo", enabled: true },
    });
    await app.inject({
      method: "DELETE",
      url: "/api/model-providers/shared/models/echo",
    });

    switchable.setActor(actor);
    const read = await app.inject({ method: "GET", url: "/api/model-default" });
    expect(JSON.parse(read.body)).toEqual({ model_ref: "shared/echo" });
  });

  it("returns 400 for malformed provider and model path keys", async () => {
    app = await appWithActor();

    const badProviderGet = await app.inject({
      method: "GET",
      url: "/api/model-providers/bad%20key",
    });
    expect(badProviderGet.statusCode).toBe(400);

    const badProviderPatch = await app.inject({
      method: "PATCH",
      url: "/api/model-providers/bad%20key",
      payload: { name: "Nope" },
    });
    expect(badProviderPatch.statusCode).toBe(400);

    const badModelDelete = await app.inject({
      method: "DELETE",
      url: "/api/model-providers/test/models/bad%20key",
    });
    expect(badModelDelete.statusCode).toBe(400);
  });

  it("clears the legacy local default when deleting the selected model", async () => {
    app = await appWithoutActor();
    await app.inject({
      method: "POST",
      url: "/api/model-providers",
      payload: { key: "local", name: "Local", kind: "test", enabled: true },
    });
    await app.inject({
      method: "POST",
      url: "/api/model-providers/local/models",
      payload: { key: "echo", name: "Echo", provider_model_id: "local-echo", enabled: true },
    });
    getRuntime().store.setSetting("org_1", "model.default_ref", "local/echo");

    const deleted = await app.inject({
      method: "DELETE",
      url: "/api/model-providers/local/models/echo",
    });

    expect(deleted.statusCode).toBe(200);
    expect(getRuntime().store.getSetting("org_1", "model.default_ref")).toBe("");
  });
});
