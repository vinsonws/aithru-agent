# Provider Model Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace model profiles with first-class model providers and provider-owned models, using `model_ref = provider_key/model_key` for chat runs.

**Architecture:** Add provider/model contracts and persistence kinds, expose dedicated provider/model settings routes, resolve `model_ref` at runtime, then update the frontend settings and composer to consume provider-grouped models. Legacy model profiles are migration input only; new runtime and UI code reads provider/model records.

**Tech Stack:** TypeScript, TypeBox, Fastify, Vitest, sql.js-backed document tables, React, React Query, existing UI primitives, Node.js `node --test` frontend source tests.

## Global Constraints

- Do not add a Python backend dependency.
- Do not add workflow, graph, scheduler, fallback-routing, marketplace, or auto-discovery behavior.
- Do not store provider API keys on model records.
- Do not expose raw API keys in API responses, logs, events, or persisted public payloads.
- Do not create a built-in default model; the default is optional `model.default_ref.{owner_user_id}` for authenticated users and `model.default_ref` only for unauthenticated local mode.
- Do not add new dependencies.
- Use existing capability/model adapter boundaries; providers configure model I/O only and do not execute tools.

---

## File Map

- `backend/packages/contracts/src/schemas.ts`: add provider/model schemas and introduce run harness `model_ref`; keep transitional `model_profile_key` until Task 3 removes runtime profile support.
- `backend/packages/contracts/src/types.ts`: export static provider/model types.
- `backend/packages/persistence/src/migrations.ts`: add `model_providers` and `model_entries` document tables plus indexes.
- `backend/packages/persistence/src/sqlite-store.ts`: map new document kinds to the new tables.
- `backend/apps/api/src/routes/model-config.ts`: new provider/model CRUD routes, default model routes, secret handling, and legacy profile migration helper.
- `backend/apps/api/src/app.ts`: register `model-config` routes.
- `backend/apps/api/src/platform-auth.ts`: classify `/api/model-providers` as settings routes.
- `backend/apps/api/src/runtime.ts`: resolve `harness_options.model_ref` to provider plus model and build the SDK adapter.
- `backend/packages/model/src/index.ts`: stop exporting the obsolete profile registry.
- Delete: `backend/packages/model/src/profiles.ts`
- `backend/tests/api/model-config-routes.test.ts`: route coverage for provider/model CRUD, secrets, org/user isolation, and default clearing.
- `backend/tests/integration/api-compat.test.ts`: update run execution tests from `model_profile_key` to `model_ref`.
- `backend/tests/persistence/sqlite-store.test.ts`: assert new dedicated tables persist provider/model documents.
- Delete: `backend/tests/model/profiles.test.ts`
- `frontend/openapi.json`: update advertised model provider/model paths and run harness schema.
- `frontend/src/lib/api/schema.d.ts`: regenerate/update generated OpenAPI types.
- `frontend/src/lib/api/types.ts`: export `AgentModelProviderEntry`, `AgentModelEntry`, and provider-with-models types.
- `frontend/src/lib/api/resources.ts`: replace `modelProfilesApi` with `modelProvidersApi`.
- `frontend/src/features/admin/ModelProfilesPage.tsx`: replace content with provider/model settings UI or rename export while keeping the settings tab import stable.
- `frontend/src/features/admin/modelProfileForm.ts`: replace with provider/model form helpers.
- `frontend/src/features/chat/composerState.ts`: use `model_ref`, provider-with-models flattening, and no-model selection helpers.
- `frontend/src/features/chat/ReferenceComposerSurface.tsx`: show provider-grouped model choices.
- `frontend/src/features/chat/ChatComposer.tsx`: query model providers and send `model_ref`.
- `frontend/src/features/conversation/NewThreadPage.tsx`: query model providers and send `model_ref`.
- `frontend/src/features/conversation/runHeaderView.ts`: display `model_ref`.
- `frontend/src/features/manager/ManagerDialogs.tsx`: rename the settings tab label key from model profiles to models.
- `frontend/src/i18n/resources/en/settings.json`, `frontend/src/i18n/resources/zh/settings.json`, `frontend/src/i18n/resources/en/chat.json`, `frontend/src/i18n/resources/zh/chat.json`: update copy.
- `frontend/tests/composer-state.test.mjs`, `frontend/tests/chat-composer-options.test.mjs`, `frontend/tests/chat-conversation-flow.test.mjs`, `frontend/tests/model-profile-form.test.mjs`, `frontend/tests/run-header-view.test.mjs`, `frontend/tests/settings-tabs.test.mjs`: update source tests.

---

### Task 1: Contracts And Persistence

**Files:**
- Modify: `backend/packages/contracts/src/schemas.ts`
- Modify: `backend/packages/contracts/src/types.ts`
- Modify: `backend/packages/persistence/src/migrations.ts`
- Modify: `backend/packages/persistence/src/sqlite-store.ts`
- Test: `backend/tests/persistence/sqlite-store.test.ts`

**Interfaces:**
- Produces: `AgentModelProviderEntry`, `AgentModelEntry`, `AgentModelProviderWithModels`, `AgentModelDefaultSelection`, `CreateModelProviderRequest`, `UpdateModelProviderRequest`, `CreateModelRequest`, `UpdateModelRequest`, `UpdateModelDefaultRequest`, `ModelSecretInput`.
- Produces document kinds: `model_provider_entry`, `model_entry`.
- Produces run option: `AgentRunHarnessOptions.model_ref?: string | null`.
- Keeps transitional run option: `AgentRunHarnessOptions.model_profile_key?: string | null` until Task 3 removes it.

- [ ] **Step 1: Write failing persistence and contract tests**

Add a test to `backend/tests/persistence/sqlite-store.test.ts`:

```ts
it("persists model providers and model entries in dedicated tables", async () => {
  const dbPath = join(tempDir, "model-config.sqlite");
  const durable = await SqliteStore.create(dbPath);
  durable.upsertDocument("model_provider_entry", "provider_org_1_deepseek", {
    id: "provider_org_1_deepseek",
    org_id: "org_1",
    owner_user_id: "user_1",
    key: "deepseek",
    name: "DeepSeek",
    kind: "openai_compatible",
    enabled: true,
    base_url: "https://api.deepseek.com",
    compat: "deepseek",
    auth_secret: { has_secret: true, secret_ref: "secret://model-providers/org_1/user_1/deepseek/api-key", redacted: true },
    metadata: null,
    created_at: "2026-07-02T00:00:00Z",
    updated_at: "2026-07-02T00:00:00Z",
  });
  durable.upsertDocument("model_entry", "model_org_1_deepseek_flash", {
    id: "model_org_1_deepseek_flash",
    org_id: "org_1",
    owner_user_id: "user_1",
    provider_key: "deepseek",
    key: "deepseek-v4-flash",
    name: "DeepSeek V4 Flash",
    provider_model_id: "deepseek-v4-flash",
    enabled: true,
    capabilities: { vision: false, thinking: true },
    request: null,
    cost_policy: null,
    selection_policy: null,
    created_at: "2026-07-02T00:00:00Z",
    updated_at: "2026-07-02T00:00:00Z",
  });
  durable.close();

  const reopened = await SqliteStore.create(dbPath);
  try {
    expect(reopened.getDocument("model_provider_entry", "provider_org_1_deepseek")?.payload).toMatchObject({
      key: "deepseek",
      kind: "openai_compatible",
    });
    expect(reopened.getDocument("model_entry", "model_org_1_deepseek_flash")?.payload).toMatchObject({
      provider_key: "deepseek",
      key: "deepseek-v4-flash",
    });
  } finally {
    reopened.close();
  }

  const SQL = await initSqlJs();
  const raw = new SQL.Database(readFileSync(dbPath));
  try {
    const tables = raw.exec("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")[0]?.values.map(([name]) => String(name)) ?? [];
    expect(tables).toEqual(expect.arrayContaining(["model_providers", "model_entries"]));
  } finally {
    raw.close();
  }
});
```

Run: `cd backend && npm run test -- tests/persistence/sqlite-store.test.ts`

Expected: FAIL because the new document kinds are stored as volatile documents and the tables do not exist.

- [ ] **Step 2: Add contract schemas**

In `backend/packages/contracts/src/schemas.ts`, add model configuration schemas near the existing core domain schemas:

```ts
export const AgentModelProviderKind = Type.Union([
  Type.Literal("openai_compatible"),
  Type.Literal("anthropic"),
  Type.Literal("test"),
]);

export const AgentModelCompatKind = Type.Union([
  Type.Literal("deepseek"),
  Type.Literal("qwen"),
  Type.Literal("minimax"),
  Type.Literal("gemini_openai_compatible"),
]);

export const AgentModelSecretStatusSchema = Type.Object({
  has_secret: Type.Boolean({ default: false }),
  secret_ref: Type.Union([Type.String(), Type.Null()]),
  redacted: Type.Boolean({ default: true }),
});

export const ModelSecretInputSchema = Type.Object({
  write_only_value: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  secret_ref: Type.Optional(Type.Union([Type.String(), Type.Null()])),
});

export const AgentModelCapabilitiesSchema = Type.Object({
  vision: Type.Boolean({ default: false }),
  thinking: Type.Boolean({ default: false }),
});

export const AgentModelProviderEntrySchema = Type.Object({
  id: Type.String(),
  org_id: Type.String(),
  owner_user_id: Type.String(),
  key: Type.String(),
  name: Type.String(),
  kind: AgentModelProviderKind,
  enabled: Type.Boolean({ default: true }),
  base_url: Type.Union([Type.String(), Type.Null()]),
  compat: Type.Union([AgentModelCompatKind, Type.Null()]),
  auth_secret: Type.Union([AgentModelSecretStatusSchema, Type.Null()]),
  metadata: Type.Union([Type.Record(Type.String(), Type.Unknown()), Type.Null()]),
  created_at: Type.String(),
  updated_at: Type.String(),
});

export const AgentModelEntrySchema = Type.Object({
  id: Type.String(),
  org_id: Type.String(),
  owner_user_id: Type.String(),
  provider_key: Type.String(),
  key: Type.String(),
  name: Type.String(),
  provider_model_id: Type.String(),
  enabled: Type.Boolean({ default: true }),
  capabilities: AgentModelCapabilitiesSchema,
  request: Type.Union([Type.Record(Type.String(), Type.Unknown()), Type.Null()]),
  cost_policy: Type.Union([Type.Record(Type.String(), Type.Unknown()), Type.Null()]),
  selection_policy: Type.Union([Type.Record(Type.String(), Type.Unknown()), Type.Null()]),
  created_at: Type.String(),
  updated_at: Type.String(),
});

export const AgentModelProviderWithModelsSchema = Type.Intersect([
  AgentModelProviderEntrySchema,
  Type.Object({
    models: Type.Array(AgentModelEntrySchema),
    default_model_ref: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  }),
]);

export const AgentModelDefaultSelectionSchema = Type.Object({
  model_ref: Type.Union([Type.String(), Type.Null()]),
});
```

Add request schemas:

```ts
export const CreateModelProviderRequestSchema = Type.Object({
  key: Type.String({ minLength: 1 }),
  name: Type.String({ minLength: 1 }),
  kind: AgentModelProviderKind,
  enabled: Type.Optional(Type.Boolean()),
  base_url: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  compat: Type.Optional(Type.Union([AgentModelCompatKind, Type.Null()])),
  auth_secret: Type.Optional(Type.Union([ModelSecretInputSchema, Type.Null()])),
  metadata: Type.Optional(Type.Union([Type.Record(Type.String(), Type.Unknown()), Type.Null()])),
});

export const UpdateModelProviderRequestSchema = Type.Partial(CreateModelProviderRequestSchema);

export const CreateModelRequestSchema = Type.Object({
  key: Type.String({ minLength: 1 }),
  name: Type.String({ minLength: 1 }),
  provider_model_id: Type.String({ minLength: 1 }),
  enabled: Type.Optional(Type.Boolean()),
  capabilities: Type.Optional(AgentModelCapabilitiesSchema),
  request: Type.Optional(Type.Union([Type.Record(Type.String(), Type.Unknown()), Type.Null()])),
  cost_policy: Type.Optional(Type.Union([Type.Record(Type.String(), Type.Unknown()), Type.Null()])),
  selection_policy: Type.Optional(Type.Union([Type.Record(Type.String(), Type.Unknown()), Type.Null()])),
});

export const UpdateModelRequestSchema = Type.Partial(CreateModelRequestSchema);

export const UpdateModelDefaultRequestSchema = Type.Object({
  model_ref: Type.Union([Type.String(), Type.Null()]),
});
```

Update `AgentRunHarnessOptionsSchema`:

```ts
model_ref: Type.Optional(Type.Union([Type.String(), Type.Null()])),
model_profile_key: Type.Optional(Type.Union([Type.String(), Type.Null()])),
```

Keep `model_profile_key` during Task 1 so the backend still typechecks before
the runtime migration. Task 3 removes it from the contract after backend tests
and runtime selection have moved to `model_ref`.

- [ ] **Step 3: Export static types**

In `backend/packages/contracts/src/types.ts`, import the new schemas and export:

```ts
export type AgentModelProviderEntry = Static<typeof AgentModelProviderEntrySchema>;
export type AgentModelEntry = Static<typeof AgentModelEntrySchema>;
export type AgentModelProviderWithModels = Static<typeof AgentModelProviderWithModelsSchema>;
export type AgentModelDefaultSelection = Static<typeof AgentModelDefaultSelectionSchema>;
export type CreateModelProviderRequest = Static<typeof CreateModelProviderRequestSchema>;
export type UpdateModelProviderRequest = Static<typeof UpdateModelProviderRequestSchema>;
export type CreateModelRequest = Static<typeof CreateModelRequestSchema>;
export type UpdateModelRequest = Static<typeof UpdateModelRequestSchema>;
export type UpdateModelDefaultRequest = Static<typeof UpdateModelDefaultRequestSchema>;
```

- [ ] **Step 4: Add persistence tables and mappings**

In `backend/packages/persistence/src/migrations.ts`, add:

```sql
CREATE TABLE IF NOT EXISTS model_providers (
  id TEXT PRIMARY KEY,
  org_id TEXT,
  owner_user_id TEXT,
  key TEXT,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_entries (
  id TEXT PRIMARY KEY,
  org_id TEXT,
  owner_user_id TEXT,
  key TEXT,
  payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_model_providers_org_key ON model_providers(org_id, key);
CREATE INDEX IF NOT EXISTS idx_model_entries_org_key ON model_entries(org_id, key);
```

In `backend/packages/persistence/src/sqlite-store.ts`, update `DOCUMENT_TABLES`:

```ts
const DOCUMENT_TABLES = {
  model_profile_entry: "model_profiles",
  model_provider_entry: "model_providers",
  model_entry: "model_entries",
  skill_registry_entry: "skill_registry_entries",
  skill_package_user: "skill_package_users",
  subagent_spec: "subagent_specs",
  external_tool_config_entry: "external_tool_configs",
  tool_call_record: "tool_call_records",
} as const;
```

- [ ] **Step 5: Run the focused check**

Run: `cd backend && npm run test -- tests/persistence/sqlite-store.test.ts`

Expected: PASS for persistence tests.

Run: `cd backend && npm run typecheck`

Expected: PASS.

---

### Task 2: Provider And Model API Routes

**Files:**
- Create: `backend/apps/api/src/routes/model-config.ts`
- Modify: `backend/apps/api/src/app.ts`
- Modify: `backend/apps/api/src/platform-auth.ts`
- Test: `backend/tests/api/model-config-routes.test.ts`
- Later API artifact files: `frontend/openapi.json`, `frontend/src/lib/api/schema.d.ts`

**Interfaces:**
- Consumes: document kinds `model_provider_entry`, `model_entry`.
- Produces: `/api/model-providers`, nested `/models` routes, and `/api/model-default`.
- Produces helpers exported from `model-config.ts`: `modelRef(providerKey: string, modelKey: string): string`, `isValidModelKey(value: string): boolean`.

- [ ] **Step 1: Write failing API route tests**

Create `backend/tests/api/model-config-routes.test.ts` with these cases:

```ts
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

  it("clears the owner-scoped default when deleting the default model", async () => {
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
});
```

Run: `cd backend && npm run test -- tests/api/model-config-routes.test.ts`

Expected: FAIL because `registerModelConfigRoutes` does not exist.

- [ ] **Step 2: Implement route helpers**

Create `backend/apps/api/src/routes/model-config.ts` with:

```ts
import { createHash } from "node:crypto";
import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getRuntime } from "../runtime.js";
import { platformActorFromRequest, requestActorUserId, platformRequestOrgId } from "../platform-auth.js";

const DEFAULT_REF_SETTING = "model.default_ref";

function defaultRefSettingKey(ownerUserId?: string): string {
  return ownerUserId ? `${DEFAULT_REF_SETTING}.${ownerUserId}` : DEFAULT_REF_SETTING;
}

export function modelRef(providerKey: string, modelKey: string): string {
  return `${providerKey}/${modelKey}`;
}

export function isValidModelKey(value: string): boolean {
  return /^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(value);
}

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function requestOrgId(request: FastifyRequest, body?: any): string {
  return platformRequestOrgId(platformActorFromRequest(request), body, request.query as any);
}

function requestOwnerUserId(request: FastifyRequest, body?: any): string {
  return requestActorUserId(platformActorFromRequest(request), body);
}

function idFor(prefix: string, orgId: string, ownerUserId: string | undefined, key: string): string {
  const digest = createHash("sha256")
    .update(ownerUserId ? `${orgId}\0${ownerUserId}\0${key}` : `${orgId}\0${key}`)
    .digest("hex")
    .slice(0, 20);
  return `${prefix}_${digest}`;
}

function secretStatus(secretRef: string | null = null) {
  return secretRef
    ? { has_secret: true, secret_ref: secretRef, redacted: true }
    : { has_secret: false, secret_ref: null, redacted: true };
}

function providerSecretRef(orgId: string, ownerUserId: string | undefined, providerKey: string): string {
  return ownerUserId
    ? `secret://model-providers/${orgId}/${ownerUserId}/${providerKey}/api-key`
    : `secret://model-providers/${orgId}/${providerKey}/api-key`;
}
```

Use these helpers inside the routes. Reject invalid provider/model keys with `400`.

- [ ] **Step 3: Implement CRUD routes**

In the same file, implement `registerModelConfigRoutes(app: FastifyInstance)`:

```ts
export function registerModelConfigRoutes(app: FastifyInstance): void {
  app.get("/api/model-providers", async (request) => listProviders(request));
  app.post("/api/model-providers", async (request, reply) => createProvider(request, reply));
  app.get("/api/model-providers/:provider_key", async (request, reply) => getProvider(request, reply));
  app.patch("/api/model-providers/:provider_key", async (request, reply) => updateProvider(request, reply));
  app.delete("/api/model-providers/:provider_key", async (request, reply) => deleteProvider(request, reply));

  app.get("/api/model-providers/:provider_key/models", async (request, reply) => listModels(request, reply));
  app.post("/api/model-providers/:provider_key/models", async (request, reply) => createModel(request, reply));
  app.get("/api/model-providers/:provider_key/models/:model_key", async (request, reply) => getModel(request, reply));
  app.patch("/api/model-providers/:provider_key/models/:model_key", async (request, reply) => updateModel(request, reply));
  app.delete("/api/model-providers/:provider_key/models/:model_key", async (request, reply) => deleteModel(request, reply));

  app.get("/api/model-default", async (request) => getDefaultModel(request));
  app.put("/api/model-default", async (request, reply) => setDefaultModel(request, reply));
}
```

The route functions should:

- scope every list by `requestOrgId(request)`;
- filter every returned record by `owner_user_id === requestOwnerUserId(request)` when there is an authenticated actor;
- write provider secrets with `getRuntime().store.setSecret(orgId, ref, writeOnlyValue)`;
- return only `secretStatus(ref)`;
- store model document `key` as full `provider/model` for SQLite index lookups;
- delete child models when deleting a provider;
- clear the owner-scoped default setting by setting it to `""` when deleting the selected provider/model.
- validate `PUT /api/model-default` by parsing `provider/model` and checking that both records exist, are enabled, and belong to the current actor.

- [ ] **Step 4: Register route and auth settings path**

In `backend/apps/api/src/app.ts`:

```ts
import { registerModelConfigRoutes } from "./routes/model-config.js";
```

Register before or after `registerCompatRoutes(app)`:

```ts
registerModelConfigRoutes(app);
```

In `backend/apps/api/src/platform-auth.ts`, update `isSettingsPath`:

```ts
"/api/model-providers",
```

Keep `/api/model-profiles` only if tests still cover legacy reads during the migration task; otherwise remove it when old routes are removed.

- [ ] **Step 5: Run focused route tests**

Run: `cd backend && npm run test -- tests/api/model-config-routes.test.ts`

Expected: PASS.

Run: `cd backend && npm run typecheck`

Expected: PASS.

---

### Task 3: Runtime Resolver And Legacy Profile Migration

**Files:**
- Modify: `backend/apps/api/src/runtime.ts`
- Modify: `backend/apps/api/src/routes/model-config.ts`
- Modify: `backend/packages/contracts/src/schemas.ts`
- Modify: `backend/packages/model/src/index.ts`
- Delete: `backend/packages/model/src/profiles.ts`
- Modify: `backend/tests/integration/api-compat.test.ts`
- Modify: `backend/tests/api/route-access.test.ts`
- Delete: `backend/tests/model/profiles.test.ts`

**Interfaces:**
- Consumes: `harness_options.model_ref`.
- Consumes provider/model document kinds.
- Produces runtime error codes: `MODEL_NOT_CONFIGURED`, `MODEL_PROVIDER_NOT_FOUND`, `MODEL_NOT_FOUND`, `MODEL_PROVIDER_DISABLED`, `MODEL_DISABLED`, `MODEL_PROVIDER_SECRET_MISSING`.

- [ ] **Step 1: Write failing runtime integration tests**

In `backend/tests/integration/api-compat.test.ts`, replace the old "executes frontend chat runs that select a model profile" test with:

```ts
it("executes frontend chat runs that select a provider model ref", async () => {
  const provider = await app.inject({
    method: "POST",
    url: "/api/model-providers",
    payload: { key: "test", name: "Test", kind: "test", enabled: true },
  });
  expect(provider.statusCode).toBe(201);

  const model = await app.inject({
    method: "POST",
    url: "/api/model-providers/test/models",
    payload: {
      key: "echo",
      name: "Echo",
      provider_model_id: "test",
      enabled: true,
      capabilities: { vision: false, thinking: false },
    },
  });
  expect(model.statusCode).toBe(201);

  const created = await app.inject({
    method: "POST",
    url: "/api/runs",
    payload: {
      task_msg: "say hi",
      org_id: "org_1",
      actor_user_id: "user_1",
      scopes: ["agent.workspace.read"],
      selected_skill_keys: null,
      harness_options: { model_ref: "test/echo" },
      wait_for_completion: false,
      persist_task_msg_message: true,
    },
  });

  expect(created.statusCode).toBe(201);
  const run = JSON.parse(created.body);
  const events = await waitForRunEvents(run.id, "run.completed");
  expect(events.map((event: any) => event.type)).toEqual(
    expect.arrayContaining(["message.delta", "message.completed", "run.completed"]),
  );
});
```

Add an isolation test:

```ts
it("does not let runs use provider models owned by another user in the same org", async () => {
  getRuntime().store.upsertDocument("model_provider_entry", "provider_foreign_runtime", {
    id: "provider_foreign_runtime",
    org_id: "org_1",
    owner_user_id: "user_2",
    key: "foreign",
    name: "Foreign",
    kind: "test",
    enabled: true,
    base_url: null,
    compat: null,
    auth_secret: null,
    metadata: null,
    created_at: "2026-07-02T00:00:00Z",
    updated_at: "2026-07-02T00:00:00Z",
  });
  getRuntime().store.upsertDocument("model_entry", "model_foreign_runtime", {
    id: "model_foreign_runtime",
    org_id: "org_1",
    owner_user_id: "user_2",
    provider_key: "foreign",
    key: "echo",
    name: "Echo",
    provider_model_id: "test",
    enabled: true,
    capabilities: { vision: false, thinking: false },
    request: null,
    cost_policy: null,
    selection_policy: null,
    created_at: "2026-07-02T00:00:00Z",
    updated_at: "2026-07-02T00:00:00Z",
  });

  const created = await app.inject({
    method: "POST",
    url: "/api/runs",
    payload: {
      task_msg: "say hi",
      org_id: "org_1",
      actor_user_id: "user_1",
      scopes: ["agent.workspace.read"],
      selected_skill_keys: null,
      harness_options: { model_ref: "foreign/echo" },
      wait_for_completion: false,
      persist_task_msg_message: true,
    },
  });

  const run = JSON.parse(created.body);
  const events = await waitForRunEvents(run.id, "run.failed");
  expect(events.find((event: any) => event.type === "run.failed")?.payload.error.code).toBe("MODEL_PROVIDER_NOT_FOUND");
});
```

Run: `cd backend && npm run test -- tests/integration/api-compat.test.ts`

Expected: FAIL because runtime still reads `model_profile_key`.

- [ ] **Step 2: Replace runtime profile resolver with provider/model resolver**

In `backend/apps/api/src/runtime.ts`, replace `StoredModelProfile` with:

```ts
type StoredModelProvider = {
  key: string;
  owner_user_id?: string;
  name?: string;
  kind?: "openai_compatible" | "anthropic" | "test";
  enabled?: boolean;
  base_url?: string | null;
  compat?: "deepseek" | "qwen" | "minimax" | "gemini_openai_compatible" | null;
  auth_secret?: { has_secret?: boolean; secret_ref?: string | null } | null;
  metadata?: Record<string, unknown> | null;
};

type StoredModelEntry = {
  provider_key: string;
  key: string;
  owner_user_id?: string;
  provider_model_id?: string;
  enabled?: boolean;
  capabilities?: { thinking?: boolean; vision?: boolean } | null;
  request?: Record<string, unknown> | null;
};
```

Replace `modelProfileKey(run)` with:

```ts
function modelRefForRun(run: AgentRun): string | null {
  const options = run.harness_options as Record<string, unknown> | null | undefined;
  return typeof options?.model_ref === "string" && options.model_ref.trim()
    ? options.model_ref.trim()
    : null;
}

function parseModelRef(value: string): { providerKey: string; modelKey: string } | null {
  const [providerKey, modelKey, extra] = value.split("/");
  return providerKey && modelKey && extra == null ? { providerKey, modelKey } : null;
}
```

Add document lookup helpers:

```ts
function storedModelProvider(store: AgentStore, orgId: string, actorUserId: string, key: string): StoredModelProvider | null {
  return store
    .listDocuments("model_provider_entry", orgId)
    .map((doc) => doc.payload as StoredModelProvider)
    .find((entry) => entry.key === key && entry.owner_user_id === actorUserId) ?? null;
}

function storedModelEntry(store: AgentStore, orgId: string, actorUserId: string, providerKey: string, modelKey: string): StoredModelEntry | null {
  return store
    .listDocuments("model_entry", orgId)
    .map((doc) => doc.payload as StoredModelEntry)
    .find((entry) => entry.provider_key === providerKey && entry.key === modelKey && entry.owner_user_id === actorUserId) ?? null;
}
```

Update `adapterForRun` to:

- fail with `MODEL_NOT_CONFIGURED` when no `model_ref`;
- parse ref and fail with `MODEL_NOT_FOUND` for malformed refs;
- load provider first, then model;
- check both `enabled` flags;
- use `defaultTestAdapter()` when provider kind is `test`;
- load provider secret for non-test providers;
- pass `provider.kind === "anthropic" ? "anthropic" : "custom"` to `createSdkModelAdapter`;
- pass `model.provider_model_id`;
- merge metadata:

```ts
const metadata = {
  ...(provider.metadata ?? {}),
  ...(provider.base_url ? { base_url: provider.base_url } : {}),
  ...(provider.compat ? { compat: provider.compat } : {}),
  ...(model.request ? { request: model.request } : {}),
};
```

After backend tests are updated to `model_ref`, remove the transitional
`model_profile_key` field from `AgentRunHarnessOptionsSchema`.

- [ ] **Step 3: Add one-time legacy migration helper**

In `backend/apps/api/src/routes/model-config.ts`, add:

```ts
function migrateLegacyModelProfilesForRequest(request: FastifyRequest): void {
  const store = getRuntime().store;
  const orgId = requestOrgId(request);
  const ownerUserId = requestOwnerUserId(request);
  const existing = store
    .listDocuments("model_provider_entry", orgId)
    .some((doc) => (doc.payload as any).owner_user_id === ownerUserId);
  if (existing) return;

  const profiles = store
    .listDocuments("model_profile_entry", orgId)
    .map((doc) => doc.payload as any)
    .filter((profile) => profile.owner_user_id === ownerUserId && typeof profile.model === "string" && profile.model.trim());

  for (const profile of profiles) {
    const strippedModel = stripKnownModelPrefix(String(profile.model));
    const providerKey = profile.metadata?.compat === "deepseek" ? "deepseek" : slugifyKey(String(profile.provider ?? "custom"));
    const providerId = idFor("model_provider", orgId, ownerUserId, providerKey);
    if (!store.getDocument("model_provider_entry", providerId)) {
      const timestamp = now();
      store.upsertDocument("model_provider_entry", providerId, {
        id: providerId,
        org_id: orgId,
        owner_user_id: ownerUserId,
        key: providerKey,
        name: providerKey === "deepseek" ? "DeepSeek" : humanizeName(providerKey),
        kind: profile.provider === "anthropic" ? "anthropic" : profile.provider === "test" ? "test" : "openai_compatible",
        enabled: profile.enabled !== false,
        base_url: profile.metadata?.base_url ?? null,
        compat: profile.metadata?.compat ?? null,
        auth_secret: profile.auth_secret ?? secretStatus(),
        metadata: null,
        created_at: timestamp,
        updated_at: timestamp,
      });
    }

    const modelKey = slugifyKey(strippedModel);
    const timestamp = now();
    store.upsertDocument("model_entry", idFor("model", orgId, ownerUserId, `${providerKey}/${modelKey}`), {
      id: idFor("model", orgId, ownerUserId, `${providerKey}/${modelKey}`),
      org_id: orgId,
      owner_user_id: ownerUserId,
      provider_key: providerKey,
      key: modelKey,
      name: profile.name ?? humanizeName(strippedModel),
      provider_model_id: strippedModel,
      enabled: profile.enabled !== false,
      capabilities: profile.capabilities ?? { vision: false, thinking: false },
      request: profile.metadata?.request ?? null,
      cost_policy: profile.cost_policy ?? null,
      selection_policy: profile.selection_policy ?? null,
      created_at: timestamp,
      updated_at: timestamp,
    });
  }
}
```

Add these local helpers next to the migration function:

```ts
function stripKnownModelPrefix(value: string): string {
  return value.replace(/^(custom|openai|anthropic|test):/, "").trim();
}

function slugifyKey(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "model";
}

function humanizeName(value: string): string {
  return stripKnownModelPrefix(value).replace(/[-_]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
```

Call this helper at the start of `GET /api/model-providers`. Do not call it from runtime; runtime reads the new model only.

- [ ] **Step 4: Update old tests to use model_ref**

Update backend tests that create runs with `harness_options: { model_profile_key: "default" }` to create a test provider/model first or set `model_ref: "test/echo"`.

Use this helper in backend tests where useful:

```ts
function seedTestModel(orgId = "org_1", ownerUserId = "user_1") {
  const timestamp = new Date().toISOString().replace(/\.\d{3}/, "");
  getRuntime().store.upsertDocument("model_provider_entry", `provider_${orgId}_${ownerUserId}_test`, {
    id: `provider_${orgId}_${ownerUserId}_test`,
    org_id: orgId,
    owner_user_id: ownerUserId,
    key: "test",
    name: "Test",
    kind: "test",
    enabled: true,
    base_url: null,
    compat: null,
    auth_secret: null,
    metadata: null,
    created_at: timestamp,
    updated_at: timestamp,
  });
  getRuntime().store.upsertDocument("model_entry", `model_${orgId}_${ownerUserId}_test_echo`, {
    id: `model_${orgId}_${ownerUserId}_test_echo`,
    org_id: orgId,
    owner_user_id: ownerUserId,
    provider_key: "test",
    key: "echo",
    name: "Echo",
    provider_model_id: "test",
    enabled: true,
    capabilities: { vision: false, thinking: false },
    request: null,
    cost_policy: null,
    selection_policy: null,
    created_at: timestamp,
    updated_at: timestamp,
  });
}
```

- [ ] **Step 5: Remove obsolete profile registry**

Delete the obsolete profile registry file and test:

```txt
backend/packages/model/src/profiles.ts
backend/tests/model/profiles.test.ts
```

In `backend/packages/model/src/index.ts`, remove:

```ts
export * from "./profiles.js";
```

- [ ] **Step 6: Run focused runtime checks**

Run: `cd backend && npm run test -- tests/integration/api-compat.test.ts tests/api/route-access.test.ts`

Expected: PASS.

Run: `cd backend && npm run typecheck`

Expected: PASS.

---

### Task 4: Frontend API, Types, And Composer State

**Files:**
- Modify: `frontend/openapi.json`
- Modify: `frontend/src/lib/api/schema.d.ts`
- Modify: `frontend/src/lib/api/types.ts`
- Modify: `frontend/src/lib/api/resources.ts`
- Modify: `frontend/src/features/chat/composerState.ts`
- Modify: `frontend/src/features/conversation/runHeaderView.ts`
- Test: `frontend/tests/composer-state.test.mjs`
- Test: `frontend/tests/chat-composer-options.test.mjs`
- Test: `frontend/tests/run-header-view.test.mjs`

**Interfaces:**
- Consumes: `AgentModelProviderWithModels[]`.
- Produces: `buildComposerHarnessOptions(modelRef, mode, reasoningLevel)` with `model_ref`.
- Produces default model API helpers.
- Produces: `flattenUsableModels(providers)` returning grouped selectable models.
- Transitional note: the old `modelProfilesApi` and profile type exports may remain in this task only so still-unmigrated UI compiles until Task 5. `AgentRunHarnessOptions` and new composer state must no longer use or expose `model_profile_key`.

- [ ] **Step 1: Write failing frontend state tests**

Update `frontend/tests/composer-state.test.mjs`:

```js
test("provider models flatten to usable model refs", async () => {
  const { flattenUsableModels, selectUsableModelRef } = await loadComposerState();
  const providers = [
    { key: "empty", name: "Empty", enabled: true, models: [] },
    {
      key: "deepseek",
      name: "DeepSeek",
      enabled: true,
      models: [
        { key: "deepseek-v4-flash", name: "Flash", provider_model_id: "deepseek-v4-flash", enabled: true },
        { key: "disabled", name: "Disabled", provider_model_id: "disabled", enabled: false },
      ],
    },
    {
      key: "off",
      name: "Off",
      enabled: false,
      models: [{ key: "model", name: "Model", provider_model_id: "model", enabled: true }],
    },
  ];

  assert.deepEqual(flattenUsableModels(providers).map((model) => model.ref), ["deepseek/deepseek-v4-flash"]);
  assert.equal(selectUsableModelRef(providers, "missing"), "deepseek/deepseek-v4-flash");
  assert.equal(selectUsableModelRef([], ""), "");
});
```

Update `frontend/tests/chat-composer-options.test.mjs` and `frontend/tests/composer-state.test.mjs` assertions from `model_profile_key` to `model_ref`.

Run: `cd frontend && npm run test -- tests/composer-state.test.mjs tests/chat-composer-options.test.mjs`

Expected: FAIL because helpers still use profiles.

- [ ] **Step 2: Update frontend type exports and resources**

In `frontend/src/lib/api/types.ts`, add provider/model exports:

```ts
export type AgentModelProviderEntry = S["AgentModelProviderEntry"];
export type AgentModelEntry = S["AgentModelEntry"];
export type AgentModelProviderWithModels = S["AgentModelProviderWithModels"];
export type AgentModelDefaultSelection = S["AgentModelDefaultSelection"];
export type CreateModelProviderRequest = S["CreateModelProviderRequest"];
export type UpdateModelProviderRequest = S["UpdateModelProviderRequest"];
export type CreateModelRequest = S["CreateModelRequest"];
export type UpdateModelRequest = S["UpdateModelRequest"];
export type UpdateModelDefaultRequest = S["UpdateModelDefaultRequest"];
```

In `frontend/src/lib/api/resources.ts`, add `modelProvidersApi`:

```ts
export const modelProvidersApi = {
  list: () => apiRequest<AgentModelProviderWithModels[]>(`/api/model-providers`),
  create: (body: CreateModelProviderRequest) =>
    apiRequest<AgentModelProviderEntry>(`/api/model-providers`, { method: "POST", body }),
  patch: (key: string, body: UpdateModelProviderRequest) =>
    apiRequest<AgentModelProviderEntry>(`/api/model-providers/${key}`, { method: "PATCH", body }),
  remove: (key: string) =>
    apiRequest<{ deleted: boolean }>(`/api/model-providers/${key}`, { method: "DELETE" }),
  createModel: (providerKey: string, body: CreateModelRequest) =>
    apiRequest<AgentModelEntry>(`/api/model-providers/${providerKey}/models`, { method: "POST", body }),
  patchModel: (providerKey: string, modelKey: string, body: UpdateModelRequest) =>
    apiRequest<AgentModelEntry>(`/api/model-providers/${providerKey}/models/${modelKey}`, { method: "PATCH", body }),
  removeModel: (providerKey: string, modelKey: string) =>
    apiRequest<{ deleted: boolean }>(`/api/model-providers/${providerKey}/models/${modelKey}`, { method: "DELETE" }),
  getDefault: () => apiRequest<AgentModelDefaultSelection>(`/api/model-default`),
  setDefault: (body: UpdateModelDefaultRequest) =>
    apiRequest<AgentModelDefaultSelection>(`/api/model-default`, { method: "PUT", body }),
};
```

Keep the legacy `modelProfilesApi` wrapper and `AgentModelProfileEntry` export only as a temporary compile bridge for UI files that Task 5 replaces. Do not use them from new composer state.

- [ ] **Step 3: Update composer state**

In `frontend/src/features/chat/composerState.ts`, replace profile helpers with:

```ts
export interface ComposerModelProvider {
  key: string;
  name?: string | null;
  enabled?: boolean;
  models?: ComposerProviderModel[];
}

export interface ComposerProviderModel {
  key: string;
  name?: string | null;
  provider_model_id?: string | null;
  enabled?: boolean;
}

export interface ComposerSelectableModel {
  ref: string;
  providerKey: string;
  providerName: string;
  modelKey: string;
  modelName: string;
  providerModelId: string;
}

export function modelRef(providerKey: string, modelKey: string): string {
  return `${providerKey}/${modelKey}`;
}

export function flattenUsableModels(
  providers: ComposerModelProvider[] | null | undefined,
): ComposerSelectableModel[] {
  return (providers ?? []).flatMap((provider) => {
    if (provider.enabled === false) return [];
    return (provider.models ?? [])
      .filter((model) => model.enabled !== false && Boolean(model.provider_model_id?.trim()))
      .map((model) => ({
        ref: modelRef(provider.key, model.key),
        providerKey: provider.key,
        providerName: provider.name || provider.key,
        modelKey: model.key,
        modelName: model.name || model.provider_model_id || model.key,
        providerModelId: model.provider_model_id || model.key,
      }));
  });
}

export function selectUsableModelRef(
  providers: ComposerModelProvider[] | null | undefined,
  currentRef: string | null | undefined,
): string {
  const usable = flattenUsableModels(providers);
  if (currentRef && usable.some((model) => model.ref === currentRef)) return currentRef;
  return usable[0]?.ref ?? "";
}
```

Update `buildComposerHarnessOptions` parameter name and output:

```ts
export function buildComposerHarnessOptions(
  modelRefValue: string | null,
  mode: string,
  reasoningLevel: string | null | undefined,
): AgentRunHarnessOptions | undefined {
  // existing mode logic
  if (modelRefValue) {
    harnessOptions.model_ref = modelRefValue;
  }
  return Object.keys(harnessOptions).length > 0 ? harnessOptions : undefined;
}
```

- [ ] **Step 4: Update run header display**

In `frontend/src/features/conversation/runHeaderView.ts`, replace model label lookup with:

```ts
return opts?.model_ref ?? opts?.model ?? "";
```

Update `frontend/tests/run-header-view.test.mjs` to assert `model_ref` precedence.

- [ ] **Step 5: Run frontend state tests**

Run: `cd frontend && npm run test -- tests/composer-state.test.mjs tests/chat-composer-options.test.mjs tests/run-header-view.test.mjs`

Expected: PASS.

---

### Task 5: Settings UI And Chat Selector

**Files:**
- Modify: `frontend/src/features/admin/ModelProfilesPage.tsx`
- Modify: `frontend/src/features/admin/modelProfileForm.ts`
- Modify: `frontend/src/features/manager/ManagerDialogs.tsx`
- Modify: `frontend/src/features/chat/ReferenceComposerSurface.tsx`
- Modify: `frontend/src/features/chat/ChatComposer.tsx`
- Modify: `frontend/src/features/conversation/NewThreadPage.tsx`
- Modify: i18n files listed in File Map
- Test: `frontend/tests/model-profile-form.test.mjs`
- Test: `frontend/tests/chat-conversation-flow.test.mjs`
- Test: `frontend/tests/settings-tabs.test.mjs`

**Interfaces:**
- Consumes: `modelProvidersApi`.
- Produces: DeepSeek preset payloads.
- Produces settings UI that creates one provider plus multiple models.
- Produces composer grouped menu over `AgentModelProviderWithModels[]`.

- [ ] **Step 1: Write failing source tests**

Replace `frontend/tests/model-profile-form.test.mjs` with provider/model helper checks:

```js
test("deepseek preset creates provider and model payloads", async () => {
  const { deepSeekPresetProvider, deepSeekPresetModels } = await loadFormHelpers();
  assert.deepEqual(deepSeekPresetProvider("sk-test"), {
    key: "deepseek",
    name: "DeepSeek",
    kind: "openai_compatible",
    enabled: true,
    base_url: "https://api.deepseek.com",
    compat: "deepseek",
    auth_secret: { write_only_value: "sk-test" },
  });
  assert.deepEqual(deepSeekPresetModels().map((model) => model.key), [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
  ]);
});

test("custom provider form builds provider and model payloads", async () => {
  const { buildCustomProviderPayload, buildModelPayload } = await loadFormHelpers();
  assert.deepEqual(buildCustomProviderPayload({
    key: "my-gateway",
    name: "My Gateway",
    baseUrl: "https://gateway.example/v1",
    apiKey: "sk-test",
  }), {
    key: "my-gateway",
    name: "My Gateway",
    kind: "openai_compatible",
    enabled: true,
    base_url: "https://gateway.example/v1",
    compat: null,
    auth_secret: { write_only_value: "sk-test" },
  });
  assert.deepEqual(buildModelPayload({
    key: "qwen3-coder",
    name: "Qwen3 Coder",
    providerModelId: "qwen3-coder",
    thinking: true,
    vision: false,
  }), {
    key: "qwen3-coder",
    name: "Qwen3 Coder",
    provider_model_id: "qwen3-coder",
    enabled: true,
    capabilities: { thinking: true, vision: false },
  });
});
```

Update `frontend/tests/chat-conversation-flow.test.mjs` source assertions to look for `selectUsableModelRef`, `modelProvidersApi.list`, and `model_ref`.

Run: `cd frontend && npm run test -- tests/model-profile-form.test.mjs tests/chat-conversation-flow.test.mjs`

Expected: FAIL.

- [ ] **Step 2: Replace form helper module**

In `frontend/src/features/admin/modelProfileForm.ts`, replace profile helpers with:

```ts
export interface CustomProviderFormValues {
  key: string;
  name: string;
  baseUrl: string;
  apiKey: string;
}

export interface ModelFormValues {
  key: string;
  name: string;
  providerModelId: string;
  thinking: boolean;
  vision: boolean;
}

export function slugifyModelKey(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "model";
}

export function deepSeekPresetProvider(apiKey: string) {
  return {
    key: "deepseek",
    name: "DeepSeek",
    kind: "openai_compatible" as const,
    enabled: true,
    base_url: "https://api.deepseek.com",
    compat: "deepseek" as const,
    ...(apiKey.trim() ? { auth_secret: { write_only_value: apiKey.trim() } } : {}),
  };
}

export function deepSeekPresetModels() {
  return [
    buildModelPayload({ key: "deepseek-v4-flash", name: "DeepSeek V4 Flash", providerModelId: "deepseek-v4-flash", thinking: true, vision: false }),
    buildModelPayload({ key: "deepseek-v4-pro", name: "DeepSeek V4 Pro", providerModelId: "deepseek-v4-pro", thinking: true, vision: false }),
  ];
}

export function buildCustomProviderPayload(values: CustomProviderFormValues) {
  return {
    key: slugifyModelKey(values.key),
    name: values.name.trim() || values.key.trim(),
    kind: "openai_compatible" as const,
    enabled: true,
    base_url: values.baseUrl.trim(),
    compat: null,
    ...(values.apiKey.trim() ? { auth_secret: { write_only_value: values.apiKey.trim() } } : {}),
  };
}

export function buildModelPayload(values: ModelFormValues) {
  return {
    key: slugifyModelKey(values.key || values.providerModelId),
    name: values.name.trim() || values.providerModelId.trim(),
    provider_model_id: values.providerModelId.trim(),
    enabled: true,
    capabilities: { thinking: values.thinking, vision: values.vision },
  };
}
```

- [ ] **Step 3: Build the Models settings UI**

In `frontend/src/features/admin/ModelProfilesPage.tsx`, keep the exported component name `ModelProfilesContent` for import stability, but make the UI provider-first:

- query `modelProvidersApi.list` with key `["model-providers"]`;
- show two empty-state buttons: DeepSeek and OpenAI-compatible;
- DeepSeek button opens a small API key form and on submit:
  1. calls `modelProvidersApi.create(deepSeekPresetProvider(apiKey))`;
  2. calls `modelProvidersApi.createModel("deepseek", model)` for each `deepSeekPresetModels()`;
  3. invalidates `["model-providers"]`;
- custom form creates provider first, then model rows;
- provider list displays provider names and count of enabled models;
- selected provider panel shows provider fields and model rows;
- model row toggles call `modelProvidersApi.patchModel(provider.key, model.key, { enabled })`;
- provider enabled toggle calls `modelProvidersApi.patch(provider.key, { enabled })`;
- "Set as default" calls `modelProvidersApi.setDefault({ model_ref: provider.key + "/" + model.key })`.

Do not add connection testing or automatic discovery.

- [ ] **Step 4: Rename settings labels**

In `frontend/src/features/manager/ManagerDialogs.tsx`, keep `value: "profiles"` for stable tab state but change i18n keys:

```ts
labelKey: "models",
descriptionKey: "modelsDescription",
```

Update settings i18n:

```json
"models": "Models",
"modelsDescription": "Configure providers and the models available to chat runs."
```

Chinese:

```json
"models": "模型",
"modelsDescription": "配置模型服务商，以及聊天可使用的模型。"
```

- [ ] **Step 5: Update composer UI and page queries**

In `frontend/src/features/chat/ReferenceComposerSurface.tsx`:

- replace `modelProfiles?: AgentModelProfileEntry[]` prop with `modelProviders?: AgentModelProviderWithModels[]`;
- replace `profileKey` with `modelRef`;
- use `flattenUsableModels(modelProviders)` for menu rows;
- group rows by `providerName`;
- on select call `onModelRefChange(model.ref)`;
- no-model message remains explicit.

In `frontend/src/features/chat/ChatComposer.tsx` and `frontend/src/features/conversation/NewThreadPage.tsx`:

- query `modelProvidersApi.list`;
- maintain `modelRef` state;
- call `selectUsableModelRef(providersQuery.data, modelRef)`;
- block send when `!modelRef`;
- call `buildComposerHarnessOptions(modelRef, mode, reasoningLevel)`.

- [ ] **Step 6: Run focused frontend checks**

Run: `cd frontend && npm run test -- tests/model-profile-form.test.mjs tests/chat-conversation-flow.test.mjs tests/settings-tabs.test.mjs tests/composer-state.test.mjs`

Expected: PASS.

Run: `cd frontend && npm run typecheck`

Expected: PASS.

---

### Task 6: OpenAPI, Full Verification, And Cleanup

**Files:**
- Modify: `frontend/openapi.json`
- Modify: `frontend/src/lib/api/schema.d.ts`
- Modify: `frontend/src/lib/api/types.ts`
- Modify: `frontend/src/lib/api/resources.ts`
- Modify: `backend/apps/api/src/routes/compat.ts`
- Modify: `docs/00-agent-harness-design.md`
- Modify: `docs/superpowers/specs/2026-07-02-provider-first-model-configuration-design.md`
- Modify: `docs/superpowers/plans/2026-07-02-provider-model-configuration.md`
- Modify: tests that still mention model profiles where the product no longer does
- Verify: backend and frontend commands

**Interfaces:**
- Produces frontend-generated types consistent with the new backend API.
- Produces no remaining runtime dependency on `model_profile_key`.

- [ ] **Step 1: Update OpenAPI artifacts**

Update the static `frontend/openapi.json` so it advertises the new
`/api/model-providers` routes, `/api/model-default`, provider/model schemas,
default-selection schemas, and `AgentRunHarnessOptions.model_ref`. Then run:

```bash
cd frontend
cp openapi.json /tmp/aithru_openapi.json
npm run gen:types
```

Expected: `frontend/src/lib/api/schema.d.ts` is generated from the updated
`frontend/openapi.json` and contains:

- `AgentModelProviderEntry`
- `AgentModelEntry`
- `AgentModelProviderWithModels`
- `AgentModelDefaultSelection`
- `CreateModelProviderRequest`
- `CreateModelRequest`
- `UpdateModelDefaultRequest`
- `AgentRunHarnessOptions` with `model_ref`

Expected: it no longer advertises product use of `model_profile_key` for new run selection.

- [ ] **Step 2: Search for stale product references**

Run:

```bash
rg -n "model_profile_key|modelProfilesApi|AgentModelProfileEntry|model profile|Model profiles" backend frontend \
  -g '!frontend/openapi.json' \
  -g '!frontend/src/lib/api/schema.d.ts'
```

Expected remaining references only in:

- migration code;
- migration tests;
- historical docs;
- deliberate user-facing migration wording if any.

Remove or rename any active runtime/UI references.

Concretely remove the transitional frontend `modelProfilesApi` wrapper and
`AgentModelProfileEntry` export after Task 5 has migrated the active UI.
Update `docs/00-agent-harness-design.md` so it describes provider-owned models
and model providers instead of saying OpenAI-compatible parameters live in model
profile metadata or that the store owns model profiles.
Keep the legacy compat cleanup in `backend/apps/api/src/routes/compat.ts` that
sets the builtin default model profile model to `""` so the legacy fallback does
not advertise a fake default model.
Stage the provider/model design spec and implementation plan with this cleanup
so the repo's tracked design docs match the provider-first runtime and UI.

- [ ] **Step 3: Run backend verification**

Run:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

Expected: all pass.

- [ ] **Step 4: Run frontend verification**

Run:

```bash
cd frontend
npm run test
npm run typecheck
npm run build
```

Expected: all pass. Existing large chunk warnings are acceptable if no errors are emitted.

- [ ] **Step 5: Manual browser smoke check**

Start the frontend dev server:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Open the app and verify:

- no configured models: composer shows no-model state and send is disabled;
- Settings -> Models empty state shows DeepSeek and OpenAI-compatible options;
- adding DeepSeek creates one provider with two models;
- composer menu groups models under DeepSeek;
- selecting `DeepSeek / deepseek-v4-flash` sends `model_ref: "deepseek/deepseek-v4-flash"` in the create-run payload.

- [ ] **Step 6: Final diff review**

Run:

```bash
git diff --stat
git diff --check
```

Expected: no whitespace errors, no unrelated `scripts/run-mock.sh` or unrelated docs changes staged or edited by this task.
