# Agent Skill Progressive Disclosure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single `skill_id` runs with multi-skill progressive disclosure driven by selected skills, visible catalogs, `skill.activated` events, and controlled `skill.load`.

**Architecture:** `AgentRun` no longer stores active skill state. Explicit skills are validated at run creation and recorded as `skill.activated` events; model-loaded skills use a harness-owned `skill.load` tool that validates visibility before emitting the same event. Context building and tool policy project active skills from the event log, so instructions, tool discovery, and tool execution share one source of truth.

**Tech Stack:** TypeScript, Fastify, TypeBox, Vitest, in-memory store, SQLite store, Vite frontend API wrappers.

## Global Constraints

- Remove `skill_id` outright; do not preserve API, contract, persistence, or frontend compatibility for it.
- Do not add Agent-owned workflow graphs, WorkflowSpec semantics, graph branch semantics, or workflow scheduler behavior.
- Do not expose skill files, scripts, resources, local filesystem access, MCP, browser automation, or network access directly to model code.
- Do not build a separate LLM classifier to choose skills before the run.
- Do not use keyword heuristics as the primary activation model.
- Do not load every `SKILL.md` body into the first model request.
- Existing uncommitted single-skill runtime-load edits in `backend/packages/harness/src/model-turn.ts`, `backend/packages/skills/src/resolver.ts`, and `backend/tests/model/skill-context.test.ts` are superseded by this plan; do not commit them as-is.

---

## File Structure

- Modify `backend/packages/contracts/src/schemas.ts` and `backend/packages/contracts/src/types.ts`: remove `skill_id`; add `selected_skill_keys` request schema and context stats shape.
- Modify `backend/packages/persistence/src/migrations.ts`, `backend/packages/persistence/src/sqlite-store.ts`, `backend/packages/persistence/src/store.ts`, and `backend/packages/persistence/src/protocols.ts`: remove persisted run skill column usage.
- Modify `backend/packages/skills/src/resolver.ts`: add visible skill catalog and multi-key resolution helpers.
- Create `backend/packages/capabilities/src/skill-state.ts`: project active skills from events for policy and harness consumers.
- Create `backend/packages/harness/src/skills.ts`: emit activation events and expose the `skill.load` tool descriptor.
- Modify `backend/packages/harness/src/context-packet.ts` and `backend/packages/harness/src/model-turn.ts`: inject multiple loaded skill instructions and handle model `skill.load`.
- Modify `backend/packages/capabilities/src/policy.ts` and `backend/packages/capabilities/src/production-router.ts`: compose policy from all active skills.
- Modify `backend/apps/api/src/routes/runs.ts` and `backend/apps/api/src/routes/compat.ts`: accept `selected_skill_keys` and emit explicit activations.
- Modify `frontend/src/lib/api/types.ts`, `frontend/src/lib/api/runs.ts`, `frontend/src/features/chat/slashCommands.ts`, `frontend/src/features/chat/ChatComposer.tsx`, and `frontend/src/features/conversation/NewThreadPage.tsx`: remove `skill_id`, pass selected skill keys, and support `/skill-key task` syntax.
- Modify tests under `backend/tests/model`, `backend/tests/capability`, `backend/tests/integration`, `backend/tests/persistence`, and `frontend/tests`.

---

### Task 1: Remove `skill_id` From Contracts And Persistence

**Files:**
- Modify: `backend/packages/contracts/src/schemas.ts`
- Modify: `backend/packages/persistence/src/migrations.ts`
- Modify: `backend/packages/persistence/src/sqlite-store.ts`
- Modify: `backend/tests/contracts/schemas.test.ts`
- Modify: `backend/tests/persistence/sqlite-store.test.ts`

**Interfaces:**
- Consumes: existing `AgentRunSchema`, `CreateRunRequestSchema`, `SqliteStore.createRun`, `SqliteStore.hydrateRun`.
- Produces: `CreateRunRequestSchema.selected_skill_keys?: string[] | null`; `AgentRun` without `skill_id`.

- [ ] **Step 1: Write failing contract tests**

Add this test to `backend/tests/contracts/schemas.test.ts`:

```ts
// Add CreateRunRequestSchema to the existing @aithru-agent/contracts import.
import { AgentRunSchema, CreateRunRequestSchema } from "@aithru-agent/contracts";

it("CreateRunRequest accepts selected_skill_keys and rejects skill_id", () => {
  expect(Value.Check(CreateRunRequestSchema, {
    org_id: "org_1",
    actor_user_id: "user_1",
    task_msg: "Research this",
    selected_skill_keys: ["deep-research", "file-report"],
  })).toBe(true);

  expect(Value.Check(CreateRunRequestSchema, {
    org_id: "org_1",
    actor_user_id: "user_1",
    task_msg: "Research this",
    skill_id: "deep-research",
  })).toBe(false);
});

it("AgentRun does not expose skill_id", () => {
  expect(Object.keys((AgentRunSchema as any).properties)).not.toContain("skill_id");
});
```

- [ ] **Step 2: Run contract test to verify it fails**

Run: `cd backend && npm run test -- tests/contracts/schemas.test.ts`

Expected: FAIL because `selected_skill_keys` is not accepted and `skill_id` still exists.

- [ ] **Step 3: Update contract schemas**

In `backend/packages/contracts/src/schemas.ts`, remove `skill_id` from `AgentRunSchema`, remove it from `CreateRunRequestSchema`, and add:

```ts
selected_skill_keys: Type.Optional(Type.Union([Type.Array(Type.String()), Type.Null()])),
```

Set `Type.Object(..., { additionalProperties: false })` on `AgentRunSchema` and `CreateRunRequestSchema` so removed fields fail validation instead of being ignored.

- [ ] **Step 4: Update SQLite schema and hydration**

In `backend/packages/persistence/src/migrations.ts`, change the `runs` DDL from:

```sql
source TEXT NOT NULL, thread_id TEXT, skill_id TEXT,
workspace_id TEXT NOT NULL, task_msg TEXT NOT NULL,
```

to:

```sql
source TEXT NOT NULL, thread_id TEXT,
workspace_id TEXT NOT NULL, task_msg TEXT NOT NULL,
```

In `backend/packages/persistence/src/sqlite-store.ts`, remove `skill_id` from the `INSERT INTO runs` column list, remove the matching placeholder and value, and remove this hydrate field:

```ts
skill_id: row.skill_id == null ? null : String(row.skill_id),
```

- [ ] **Step 5: Update persistence tests**

In `backend/tests/persistence/sqlite-store.test.ts`, add:

```ts
it("stores runs without a skill_id column", async () => {
  const store = await SqliteStore.create(":memory:");
  const run = store.createRun({
    id: "run_no_skill_id",
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "chat",
    thread_id: null,
    workspace_id: "ws_1",
    task_msg: "hello",
    scopes: ["*"],
    harness_options: null,
    status: "queued",
    current_approval_id: null,
    started_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    claim: null,
    result: null,
    error: null,
  });

  expect("skill_id" in run).toBe(false);
  expect("skill_id" in store.getRun("run_no_skill_id")!).toBe(false);
  store.close();
});
```

- [ ] **Step 6: Run task verification**

Run:

```bash
cd backend
npm run test -- tests/contracts/schemas.test.ts tests/persistence/sqlite-store.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/packages/contracts/src/schemas.ts backend/packages/contracts/src/types.ts backend/packages/persistence/src/migrations.ts backend/packages/persistence/src/sqlite-store.ts backend/tests/contracts/schemas.test.ts backend/tests/persistence/sqlite-store.test.ts
git commit -m "refactor: remove run skill_id contract"
```

---

### Task 2: Add Skill Catalog And Activation Projection

**Files:**
- Modify: `backend/packages/skills/src/resolver.ts`
- Create: `backend/packages/capabilities/src/skill-state.ts`
- Create: `backend/packages/harness/src/skills.ts`
- Modify: `backend/packages/capabilities/src/index.ts`
- Modify: `backend/packages/harness/src/index.ts`
- Modify: `backend/tests/skills/loader.test.ts`
- Create: `backend/tests/model/skill-activation-state.test.ts`

**Interfaces:**
- Consumes: `SkillResolver.resolve(key, orgId, actorUserId)` and `AgentStreamEvent`.
- Produces: `SkillResolver.listVisible(orgId, actorUserId): SkillCatalogEntry[]`; `activeSkillKeysFromEvents(events): string[]` exported from capabilities; `skillLoadToolDescriptor`; `emitSkillActivated(args): void`.

- [ ] **Step 1: Write failing activation state tests**

Create `backend/tests/model/skill-activation-state.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { AgentStreamEvent } from "@aithru-agent/contracts";
import { activeSkillKeysFromEvents } from "@aithru-agent/capabilities";

function event(sequence: number, key: string): AgentStreamEvent {
  return {
    id: `evt_${sequence}`,
    run_id: "run_1",
    thread_id: null,
    sequence,
    timestamp: "2026-01-01T00:00:00Z",
    type: "skill.activated",
    source: { kind: "harness", id: null, name: null },
    visibility: "audit",
    redaction: "none",
    summary: null,
    payload: { key, trigger: "explicit" },
  };
}

describe("skill activation state", () => {
  it("projects ordered unique active skill keys from events", () => {
    expect(activeSkillKeysFromEvents([
      event(1, "deep-research"),
      event(2, "file-report"),
      event(3, "deep-research"),
    ])).toEqual(["deep-research", "file-report"]);
  });
});
```

- [ ] **Step 2: Run activation state test to verify it fails**

Run: `cd backend && npm run test -- tests/model/skill-activation-state.test.ts`

Expected: FAIL because `activeSkillKeysFromEvents` does not exist.

- [ ] **Step 3: Implement active skill projection and harness skill helpers**

Create `backend/packages/capabilities/src/skill-state.ts` and export it from `backend/packages/capabilities/src/index.ts`:

```ts
import type { AgentStreamEvent } from "@aithru-agent/contracts";
import { EVENT_TYPES } from "@aithru-agent/stream";

export function activeSkillKeysFromEvents(events: AgentStreamEvent[]): string[] {
  const keys: string[] = [];
  for (const event of events) {
    if (event.type !== EVENT_TYPES.SKILL_ACTIVATED) continue;
    const key = (event.payload as any)?.key;
    if (typeof key === "string" && key && !keys.includes(key)) keys.push(key);
  }
  return keys;
}
```

Then create `backend/packages/harness/src/skills.ts`:

```ts
import type { AgentEventWriter } from "@aithru-agent/stream";
import { EVENT_TYPES, VISIBILITY } from "@aithru-agent/stream";

export type SkillActivationTrigger = "explicit" | "slash" | "model_load";

export const skillLoadToolDescriptor = {
  name: "skill.load",
  description: "Load an available Agent Skill by key for this run.",
  input_schema: {
    type: "object",
    properties: { key: { type: "string" } },
    required: ["key"],
  },
};

export function emitSkillActivated(args: {
  eventWriter: AgentEventWriter;
  runId: string;
  threadId: string | null;
  key: string;
  name: string;
  source: string;
  version: string;
  trigger: SkillActivationTrigger;
  allowedTools: string[];
  deniedTools: string[];
}): void {
  args.eventWriter.write(
    args.runId,
    args.threadId,
    EVENT_TYPES.SKILL_ACTIVATED,
    {
      key: args.key,
      name: args.name,
      source: args.source,
      version: args.version,
      trigger: args.trigger,
      policy: {
        allowed_tools: args.allowedTools,
        denied_tools: args.deniedTools,
      },
    },
    { visibility: VISIBILITY.AUDIT, source: { kind: "harness" } },
  );
}
```

Export it from `backend/packages/harness/src/index.ts`:

```ts
export * from "./skills.js";
```

- [ ] **Step 4: Add visible catalog to SkillResolver**

In `backend/packages/skills/src/resolver.ts`, add:

```ts
export interface SkillCatalogEntry {
  key: string;
  name: string;
  description: string | null;
  source: ResolvedSkill["source"];
  version: string;
}

export function skillCatalogEntry(skill: ResolvedSkill): SkillCatalogEntry {
  return {
    key: skill.key,
    name: skill.name,
    description: skill.description,
    source: skill.source,
    version: skill.version,
  };
}
```

Add this method on `SkillResolver`:

```ts
listVisible(orgId: string, actorUserId: string): SkillCatalogEntry[] {
  const keys = new Set<string>();
  for (const pkg of this.builtins.list()) keys.add(pkg.key);
  for (const doc of this.store.listDocuments("skill_registry_entry")) {
    const entry = doc.payload as SkillEntryPayload;
    if ((entry as any).org_id === orgId && entry.key) keys.add(entry.key);
  }
  for (const doc of this.store.listDocuments("skill_package_user")) {
    const entry = doc.payload as SkillEntryPayload;
    if ((entry as any).org_id === orgId && (entry as any).owner_user_id === actorUserId && entry.key) {
      keys.add(entry.key);
    }
  }
  return [...keys]
    .map((key) => this.resolve(key, orgId, actorUserId))
    .filter((skill): skill is ResolvedSkill => skill !== null)
    .map(skillCatalogEntry);
}
```

- [ ] **Step 5: Add resolver catalog test**

Add to `backend/tests/skills/loader.test.ts`:

```ts
// Add these imports at the top of the file:
import { InMemoryStore } from "@aithru-agent/persistence";
import { SkillResolver } from "@aithru-agent/skills";

it("lists visible skill catalog without instructions", () => {
  const registry = new SkillRegistry();
  registry.register({
    key: "catalog-skill",
    path: "/skills/catalog-skill",
    name: "Catalog Skill",
    description: "Visible metadata.",
    version: "1.0.0",
    status: "published",
    enabled: true,
    allowed_tools: [],
    denied_tools: [],
    instructions: "secret body",
    resources: { references: [], scripts: [], assets: [], examples: [] },
  });
  const resolver = new SkillResolver(registry, new InMemoryStore());

  expect(resolver.listVisible("org_1", "user_1")).toEqual([{
    key: "catalog-skill",
    name: "Catalog Skill",
    description: "Visible metadata.",
    source: "builtin",
    version: "1.0.0",
  }]);
});
```

- [ ] **Step 6: Run task verification**

Run:

```bash
cd backend
npm run test -- tests/model/skill-activation-state.test.ts tests/skills/loader.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/packages/skills/src/resolver.ts backend/packages/capabilities/src/skill-state.ts backend/packages/capabilities/src/index.ts backend/packages/harness/src/skills.ts backend/packages/harness/src/index.ts backend/tests/skills/loader.test.ts backend/tests/model/skill-activation-state.test.ts
git commit -m "feat: add skill catalog activation state"
```

---

### Task 3: Load Selected Skills At Run Creation

**Files:**
- Modify: `backend/apps/api/src/routes/runs.ts`
- Modify: `backend/apps/api/src/routes/compat.ts`
- Modify: `backend/tests/integration/api.test.ts`
- Modify: `backend/tests/integration/api-compat.test.ts`

**Interfaces:**
- Consumes: `CreateRunRequest.selected_skill_keys`; `SkillResolver.resolve`; `emitSkillActivated`.
- Produces: selected skills validated before run persistence and recorded as `skill.activated` before run execution.

- [ ] **Step 1: Write failing API integration tests**

Add to `backend/tests/integration/api.test.ts`:

```ts
it("POST /api/runs activates selected skills before model execution", async () => {
  const res = await app.inject({
    method: "POST",
    url: "/api/runs",
    payload: {
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "chat",
      task_msg: "Surprise me",
      selected_skill_keys: ["surprise-me", "surprise-me"],
      harness_options: { model_profile_key: "default" },
      wait_for_completion: true,
    },
  });

  expect(res.statusCode).toBe(201);
  const run = JSON.parse(res.body);
  const events = getRuntime().store.listEvents(run.id);
  expect(events.filter((event) => event.type === "skill.activated").map((event) => (event.payload as any).key))
    .toEqual(["surprise-me"]);
  expect(events.find((event) => event.type === "skill.activated")?.sequence)
    .toBeLessThan(events.find((event) => event.type === "run.started")!.sequence);
});

it("POST /api/runs rejects unknown selected skills", async () => {
  const res = await app.inject({
    method: "POST",
    url: "/api/runs",
    payload: {
      org_id: "org_1",
      actor_user_id: "user_1",
      task_msg: "Use a missing skill",
      selected_skill_keys: ["missing-skill"],
    },
  });

  expect(res.statusCode).toBe(400);
  expect(JSON.parse(res.body)).toEqual({ error: "Skill not found: missing-skill" });
});
```

- [ ] **Step 2: Run API tests to verify they fail**

Run: `cd backend && npm run test -- tests/integration/api.test.ts`

Expected: FAIL because selected skills are not validated or activated.

- [ ] **Step 3: Add selected skill normalization helper in both route modules**

In `backend/apps/api/src/routes/runs.ts` and `backend/apps/api/src/routes/compat.ts`, add:

```ts
function selectedSkillKeys(body: any): string[] {
  const raw = Array.isArray(body.selected_skill_keys) ? body.selected_skill_keys : [];
  return [...new Set(raw.filter((key: unknown): key is string => typeof key === "string" && key.trim()).map((key) => key.trim()))];
}
```

- [ ] **Step 4: Validate before creating the run and emit selected skill activations**

In both create-run paths, resolve all selected skills before `runtime.store.createRun(run)`. If any key is unknown, return 400 before persisting the run or writing `run.created`:

```ts
const selectedSkills = [];
for (const key of selectedSkillKeys(body)) {
  const skill = runtime.skillResolver.resolve(key, orgId, actorUserId);
  if (!skill) {
    reply.code(400);
    return { error: `Skill not found: ${key}` };
  }
  selectedSkills.push(skill);
}
```

After `runtime.store.createRun(run)` and after `run.created`, emit one activation for each resolved selected skill:

```ts
for (const skill of selectedSkills) {
  emitSkillActivated({
    eventWriter: runtime.eventWriter,
    runId: run.id,
    threadId: run.thread_id ?? null,
    key: skill.key,
    name: skill.name,
    source: skill.source,
    version: skill.version,
    trigger: "explicit",
    allowedTools: skill.allowed_tools,
    deniedTools: skill.denied_tools,
  });
}
```

Import `emitSkillActivated` from `@aithru-agent/harness`.

- [ ] **Step 5: Run task verification**

Run:

```bash
cd backend
npm run test -- tests/integration/api.test.ts tests/integration/api-compat.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/api/src/routes/runs.ts backend/apps/api/src/routes/compat.ts backend/tests/integration/api.test.ts backend/tests/integration/api-compat.test.ts
git commit -m "feat: activate selected run skills"
```

---

### Task 4: Compose Multi-Skill Tool Policy

**Files:**
- Modify: `backend/packages/capabilities/src/policy.ts`
- Modify: `backend/packages/capabilities/src/production-router.ts`
- Modify: `backend/tests/capability/skill-policy.test.ts`
- Modify: `backend/tests/capability/production-router.test.ts`

**Interfaces:**
- Consumes: `activeSkillKeysFromEvents(events)` from capabilities and `SkillResolver.resolve`.
- Produces: `resolveSkillPolicy` where denied tools are unioned and allowed tools are intersected across active skills.

- [ ] **Step 1: Write failing policy composition tests**

Add to `backend/tests/capability/skill-policy.test.ts`:

```ts
// Add resolveSkillPolicy to the existing @aithru-agent/capabilities import.
import { resolveSkillPolicy } from "@aithru-agent/capabilities";

it("intersects allowlists and unions denylists across loaded skills", () => {
  const policy = resolveSkillPolicy([
    { allowed_tools: ["workspace.list_files", "workspace.read_file"], denied_tools: ["workspace.delete_file"] },
    { allowed_tools: ["workspace.read_file", "workspace.write_file"], denied_tools: ["workspace.write_file"] },
  ]);

  expect([...policy.allowedTools]).toEqual(["workspace.read_file"]);
  expect([...policy.deniedTools].sort()).toEqual(["workspace.delete_file", "workspace.write_file"]);
});
```

- [ ] **Step 2: Run policy test to verify it fails**

Run: `cd backend && npm run test -- tests/capability/skill-policy.test.ts`

Expected: FAIL because allowlists are currently unioned.

- [ ] **Step 3: Implement conservative policy composition**

In `backend/packages/capabilities/src/policy.ts`, replace `resolveSkillPolicy` with:

```ts
export function resolveSkillPolicy(
  skillConfigs: Array<{ allowed_tools?: string[]; denied_tools?: string[] }>,
): SkillPolicy {
  const deniedTools = new Set<string>();
  const allowSets = skillConfigs
    .map((config) => new Set(config.allowed_tools ?? []))
    .filter((set) => set.size > 0);

  for (const config of skillConfigs) {
    for (const tool of config.denied_tools || []) deniedTools.add(tool);
  }

  const allowedTools = new Set<string>();
  if (allowSets.length > 0) {
    const [first, ...rest] = allowSets;
    for (const tool of first) {
      if (rest.every((set) => set.has(tool)) && !deniedTools.has(tool)) allowedTools.add(tool);
    }
  }

  return { allowedTools, deniedTools };
}
```

- [ ] **Step 4: Use active skill events in ProductionCapabilityRouter**

In `backend/packages/capabilities/src/production-router.ts`, import `activeSkillKeysFromEvents` from local `./skill-state.js`. Replace `skillPolicyForRun` with a version that resolves every active key:

```ts
private skillPolicyForRun(run: { id: string; org_id: string; actor_user_id: string }): SkillPolicy | null {
  if (!this.skillResolver) return null;
  const keys = activeSkillKeysFromEvents(this.store.listEvents(run.id));
  const configs = keys
    .map((key) => this.skillResolver!.resolve(key, run.org_id, run.actor_user_id))
    .filter((skill): skill is NonNullable<typeof skill> => skill !== null)
    .map((skill) => ({ allowed_tools: skill.allowed_tools, denied_tools: skill.denied_tools }));
  return configs.length ? resolveSkillPolicy(configs) : null;
}
```

- [ ] **Step 5: Run task verification**

Run:

```bash
cd backend
npm run test -- tests/capability/skill-policy.test.ts tests/capability/production-router.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/packages/capabilities/src/policy.ts backend/packages/capabilities/src/production-router.ts backend/tests/capability/skill-policy.test.ts backend/tests/capability/production-router.test.ts
git commit -m "feat: compose active skill tool policy"
```

---

### Task 5: Inject Multiple Skill Instructions And Handle `skill.load`

**Files:**
- Modify: `backend/packages/harness/src/context-packet.ts`
- Modify: `backend/packages/harness/src/model-turn.ts`
- Modify: `backend/tests/model/skill-context.test.ts`
- Create: `backend/tests/model/skill-load-tool.test.ts`

**Interfaces:**
- Consumes: `activeSkillKeysFromEvents` from capabilities, `emitSkillActivated`, `skillLoadToolDescriptor`, `SkillResolver.listVisible`, `SkillResolver.resolve`.
- Produces: model context stats `active_skill_keys: string[]`; visible catalog metadata; `skill.load` tool result.

- [ ] **Step 1: Write failing context test**

Replace single-skill assertions in `backend/tests/model/skill-context.test.ts` with:

```ts
expect(systemMsg.content).toContain("Active skills:");
expect(systemMsg.content).toContain("## File Report");
expect(stats.active_skill_keys).toEqual(["file-report"]);
expect(JSON.stringify(stats)).not.toContain("Read files and write a report.");
```

Remove the runtime-load-by-name test; model-driven loading is covered by `skill.load`.

- [ ] **Step 2: Write failing `skill.load` model test**

Create `backend/tests/model/skill-load-tool.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import { ModelTurnLoop } from "@aithru-agent/harness";
import { TestModelAdapter } from "@aithru-agent/model";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import { SkillRegistry, SkillResolver } from "@aithru-agent/skills";

describe("skill.load", () => {
  it("loads a visible skill once and includes it on the next model turn", async () => {
    const store = new InMemoryStore();
    const registry = new SkillRegistry();
    registry.register({
      key: "deep-research",
      path: "/skills/deep-research",
      name: "Deep Research",
      description: "Research with evidence.",
      version: "0.0.0",
      status: "published",
      enabled: true,
      allowed_tools: [],
      denied_tools: [],
      instructions: "Use evidence and cite sources.",
      resources: { references: [], scripts: [], assets: [], examples: [] },
    });
    const resolver = new SkillResolver(registry, store);
    const eventWriter = new AgentEventWriter(store);
    const run = {
      id: "run_skill_load",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "chat" as const,
      thread_id: null,
      workspace_id: "ws_1",
      task_msg: "Research this",
      scopes: ["*"],
      harness_options: { model_profile_key: "default" },
      status: "queued" as const,
      current_approval_id: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    };
    store.createRun(run);

    let secondTurnSystem = "";
    const loop = new ModelTurnLoop({
      store,
      eventWriter,
      capabilityRouter: new ProductionCapabilityRouter(store, eventWriter, resolver),
      skillResolver: resolver,
      modelAdapter: new TestModelAdapter([
        [{ type: "tool_call", id: "load_1", name: "skill.load", input: { key: "deep-research" } }],
        (input) => {
          secondTurnSystem = input.messages.find((m) => m.role === "system")?.content ?? "";
          return [{ type: "text_delta", delta: "done" }, { type: "completed" }];
        },
      ]),
    });

    await loop.execute(run);

    expect(secondTurnSystem).toContain("Deep Research");
    expect(secondTurnSystem).toContain("Use evidence and cite sources.");
    expect(store.listEvents(run.id).filter((event) => event.type === EVENT_TYPES.SKILL_ACTIVATED)).toHaveLength(1);
  });
});
```

- [ ] **Step 3: Run model tests to verify they fail**

Run:

```bash
cd backend
npm run test -- tests/model/skill-context.test.ts tests/model/skill-load-tool.test.ts
```

Expected: FAIL because context still accepts one skill and `skill.load` is not handled.

- [ ] **Step 4: Update context packet**

Change `buildModelContextPacket` args to:

```ts
skillInstructions?: Array<{ name: string; instructions: string }>;
skillCatalog?: Array<{ key: string; name: string; description: string | null }>;
activeSkillKeys?: string[];
```

Render loaded instructions as:

```ts
if (args.skillInstructions?.length) {
  contextParts.push([
    "Active skills:",
    ...args.skillInstructions.map((skill) => `## ${skill.name}\n${skill.instructions}`),
  ].join("\n\n"));
}
if (args.skillCatalog?.length) {
  contextParts.push([
    "Available skills:",
    ...args.skillCatalog.map((skill) => `- ${skill.key}: ${skill.name}${skill.description ? ` — ${skill.description}` : ""}`),
    "Use skill.load with a skill key when a skill's full instructions are needed.",
  ].join("\n"));
}
```

Change stats field to:

```ts
active_skill_keys: args.activeSkillKeys ?? [],
visible_skill_count: args.skillCatalog?.length ?? 0,
```

- [ ] **Step 5: Handle `skill.load` inside ModelTurnLoop**

In `backend/packages/harness/src/model-turn.ts`, import `activeSkillKeysFromEvents` from `@aithru-agent/capabilities`, then delete `resolveSkill`. In each turn:

```ts
const activeKeys = activeSkillKeysFromEvents(this.deps.store.listEvents(run.id));
const loadedSkills = activeKeys
  .map((key) => this.deps.skillResolver?.resolve(key, currentRun.org_id, currentRun.actor_user_id))
  .filter((skill): skill is NonNullable<typeof skill> => skill !== null);
const catalog = this.deps.skillResolver?.listVisible(currentRun.org_id, currentRun.actor_user_id) ?? [];
```

Append `skillLoadToolDescriptor` to model tools:

```ts
const toolCatalog = [...tools, skillLoadToolDescriptor];
```

Before `loop.executeToolCall`, intercept:

```ts
if (event.name === "skill.load") {
  const result = this.loadSkillForRun(currentRun, event.input);
  nextToolResults.push({ id: event.id, name: event.name, input: event.input, output: result });
  continue;
}
```

Add:

```ts
private loadSkillForRun(run: AgentRun, input: Record<string, unknown>): { loaded: boolean; key?: string; error?: string } {
  const key = typeof input.key === "string" ? input.key.trim() : "";
  if (!key) return { loaded: false, error: "key is required" };
  const active = activeSkillKeysFromEvents(this.deps.store.listEvents(run.id));
  if (active.includes(key)) return { loaded: true, key };
  const skill = this.deps.skillResolver?.resolve(key, run.org_id, run.actor_user_id);
  if (!skill) return { loaded: false, key, error: `Skill not found: ${key}` };
  emitSkillActivated({
    eventWriter: this.deps.eventWriter,
    runId: run.id,
    threadId: run.thread_id ?? null,
    key: skill.key,
    name: skill.name,
    source: skill.source,
    version: skill.version,
    trigger: "model_load",
    allowedTools: skill.allowed_tools,
    deniedTools: skill.denied_tools,
  });
  return { loaded: true, key: skill.key };
}
```

- [ ] **Step 6: Run task verification**

Run:

```bash
cd backend
npm run test -- tests/model/skill-context.test.ts tests/model/skill-load-tool.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/packages/harness/src/context-packet.ts backend/packages/harness/src/model-turn.ts backend/tests/model/skill-context.test.ts backend/tests/model/skill-load-tool.test.ts
git commit -m "feat: load skills during model turns"
```

---

### Task 6: Update Frontend API Calls And Slash Skill Selection

**Files:**
- Modify: `frontend/src/lib/api/types.ts`
- Modify: `frontend/src/lib/api/runs.ts`
- Modify: `frontend/src/features/chat/slashCommands.ts`
- Modify: `frontend/src/features/chat/ChatComposer.tsx`
- Modify: `frontend/src/features/conversation/NewThreadPage.tsx`
- Modify: `frontend/tests/slash-commands.test.mjs`
- Modify: `frontend/tests/runs-api.test.mjs`
- Modify: `frontend/tests/chat-composer-options.test.mjs`

**Interfaces:**
- Consumes: `CreateRunRequest.selected_skill_keys`.
- Produces: composer sends `selected_skill_keys` and never sends `skill_id`.

- [ ] **Step 1: Write failing slash command test**

Add to `frontend/tests/slash-commands.test.mjs`:

```js
test("unknown slash token selects a skill and sends the remaining task", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/deep-research climate risk", { activeRunTaskMsg: null }), {
    kind: "send",
    taskMsg: "climate risk",
    selectedSkillKeys: ["deep-research"],
  });
});
```

Update the existing unknown slash command test expectation to:

```js
assert.deepEqual(parseSlashCommand("/unknown do something", { activeRunTaskMsg: null }), {
  kind: "send",
  taskMsg: "do something",
  selectedSkillKeys: ["unknown"],
});
```

- [ ] **Step 2: Run slash test to verify it fails**

Run: `cd frontend && npm test -- tests/slash-commands.test.mjs`

Expected: FAIL because unknown slash commands are still plain text.

- [ ] **Step 3: Update slash command result type**

In `frontend/src/features/chat/slashCommands.ts`, change send result to:

```ts
| { kind: "send"; taskMsg: string; modeOverride?: ComposerMode; selectedSkillKeys?: string[] }
```

At the bottom of `parseSlashCommand`, replace the unknown slash return with:

```ts
const skillKey = command.slice(1);
if (/^[a-z0-9][a-z0-9-]*$/.test(skillKey)) {
  return { kind: "send", taskMsg: body || input, selectedSkillKeys: [skillKey] };
}

return { kind: "send", taskMsg: input };
```

- [ ] **Step 4: Remove `skill_id` from frontend request bodies**

In `ChatComposer.tsx` and `NewThreadPage.tsx`, add `selectedSkillKeys` to mutation variables and send:

```ts
selected_skill_keys: vars.selectedSkillKeys,
```

Remove:

```ts
skill_id: null,
```

When calling `createRun.mutate`, pass:

```ts
selectedSkillKeys: command.kind === "send" ? command.selectedSkillKeys ?? [] : [],
```

- [ ] **Step 5: Run frontend verification**

Run:

```bash
cd frontend
npm test -- tests/slash-commands.test.mjs tests/runs-api.test.mjs tests/chat-composer-options.test.mjs
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api/types.ts frontend/src/lib/api/runs.ts frontend/src/features/chat/slashCommands.ts frontend/src/features/chat/ChatComposer.tsx frontend/src/features/conversation/NewThreadPage.tsx frontend/tests/slash-commands.test.mjs frontend/tests/runs-api.test.mjs frontend/tests/chat-composer-options.test.mjs
git commit -m "feat: send selected skill keys from composer"
```

---

### Task 7: Remove Remaining `skill_id` References And Update Docs

**Files:**
- Modify: `docs/04-skill-spec.md`
- Modify: `docs/03-stream-protocol.md`
- Modify: `docs/00-agent-harness-design.md`
- Modify: `README.md`
- Modify: every source/test file returned by `rg -n "skill_id" backend frontend docs README.md`

**Interfaces:**
- Consumes: all earlier tasks.
- Produces: no code, docs, generated schema, or frontend type references to `skill_id`.

- [ ] **Step 1: Run reference scan**

Run:

```bash
rg -n "skill_id" backend frontend docs README.md
```

Expected: matches remain in docs and legacy tests before this task.

- [ ] **Step 2: Replace docs wording**

In docs, replace references to `skill_id` with `selected_skill_keys`, `active_skill_keys`, or `skill.activated` depending on the sentence:

```md
User-selected skills (`selected_skill_keys`) are active from run start.
Loaded skills are projected from `skill.activated` events.
```

For stream protocol tables, use:

```md
| `skill.activated` | ✅ | `key`, `trigger`, `source`, `version`, `policy` |
```

- [ ] **Step 3: Update generated frontend API schema**

Regenerate or manually edit `frontend/src/lib/api/schema.d.ts` and `frontend/openapi.json` so:

```txt
skill_id
```

does not appear, and:

```txt
selected_skill_keys
active_skill_keys
```

appear in the relevant request/read-model shapes.

- [ ] **Step 4: Run absence check**

Run:

```bash
rg -n "skill_id" backend frontend docs README.md
```

Expected: no output.

- [ ] **Step 5: Run full backend verification**

Run:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

Expected: PASS.

- [ ] **Step 6: Run targeted frontend verification**

Run:

```bash
cd frontend
npm test -- tests/slash-commands.test.mjs tests/runs-api.test.mjs tests/chat-composer-options.test.mjs
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/04-skill-spec.md docs/03-stream-protocol.md docs/00-agent-harness-design.md README.md frontend/openapi.json frontend/src/lib/api/schema.d.ts backend frontend
git commit -m "chore: remove skill_id references"
```
