# User & Tenant Isolation Implementation Roadmap

Status: accepted
Date: 2026-07-02

## Purpose

This document defines the implementation roadmap for full user (actor) and tenant
(org) isolation across the Agent harness. The analysis enumerates 20 isolation
gaps across storage, runtime, and API layers, then proposes a phased
implementation sequence from storage schema fixes to runtime enforcement.

---

## Current State & Gap Summary

Platform auth already verifies JWTs at the Fastify HTTP boundary
([`platform-auth.ts`](../apps/api/src/platform-auth.ts)), deriving `orgId` and
actor identity from verified tokens. The gap is that this identity:

1. never reaches the storage layer (secrets, settings, memory are global);
2. reaches some routes but isn't enforced (thread GET/PATCH, run cancel, approval
   resolve);
3. reaches the Capability Router's `RunContext` but `RunContext` carries no user
   identity;
4. is lost for all sub-entities (messages, todos, events, workspace files).

The following table summarizes the 20 gaps discovered in the codebase audit:

| # | Component | Issue | Severity |
|---|-----------|-------|----------|
| 1 | Secrets store | No `org_id` column; flat global map | P0 |
| 2 | Settings store | No `org_id` column; flat global map | P0 |
| 3 | `LocalMemoryProvider` | No thread/org/user scoping; flat global map | P0 |
| 4 | Documents store `listDocuments` | Returns all rows; route does manual filter | P1 |
| 5 | `GET/PATCH /api/threads/:id` | No `owner_user_id` check | P1 |
| 6 | `GET/POST /api/runs/:id/*` | No `actor_user_id` check | P1 |
| 7 | `POST /api/approvals/:id/resolve` | Any user can resolve any approval | P1 |
| 8 | `AgentMessage` schema | No `org_id` nor `actor_user_id` | P2 |
| 9 | `AgentStreamEvent` schema | No `org_id` nor `actor_user_id` | P2 |
| 10 | `AgentTodo` schema | No `org_id` nor `actor_user_id` | P2 |
| 11 | `AgentApproval` schema | No `org_id` | P2 |
| 12 | `AgentContextSummary` schema | Has `org_id` but no `actor_user_id` | P2 |
| 13 | Workspace files | No org/user binding on `workspace_id` | P2 |
| 14 | Global `_runtime` singleton | All orgs share one store/router | P1 |
| 15 | Global `activeRuns` map | Cross-user cancel possible | P1 |
| 16 | `RunContext` | Carries no requesting user identity | P2 |
| 17 | Model profiles route | Org-level only; no user ownership | P2 |
| 18 | Skills route | `saveSkillRegistryEntry` no user check | P2 |
| 19 | External tools route | Org-level only; hardcoded `"user_1"` | P2 |
| 20 | Subagent specs route | Org-level only; no user ownership | P2 |

---

## Design Principles

1. **Identity flows from the HTTP boundary inward.** Platform auth derives
   `CurrentActor`; every downstream layer receives a typed actor context, never
   raw headers or request-body fields.
2. **Store isolation is structural, not convention-based.** Secrets, settings,
   and documents carry `org_id` (and `owner_user_id` where applicable) as schema
   columns. Queries filter on them; inserts populate them. No route should need
   to manually filter after a full-table scan.
3. **User-level isolation within an org.** Two users in the same org should not
   see each other's runs, threads, model profiles, or skill packages unless the
   org has an explicit sharing model (out of scope for this phase).
4. **No breaking schema change for existing runs/threads.** Migration populates
   `org_id` / `actor_user_id` from existing `AgentRun` / `AgentThread` records
   for child entities.
5. **The runtime may remain a singleton** for now, but resource maps within it
   (active runs, memory provider, etc.) become org-keyed.

---

## Phase 1 — Storage Schema Hardening (P0–P1)

Fix the persistence layer so every stored entity carries tenant and user
identity, and store queries enforce isolation structurally.

### Item 1.1: Add `org_id` to Secrets Table

**Problem:** [`sqlite-store.ts#L570-L619`](../../backend/packages/persistence/src/sqlite-store.ts#L570-L619)
— `secrets` table has no `org_id`. All orgs share one global secret namespace.

**What to do:**

1. Add `org_id TEXT NOT NULL DEFAULT ''` column to `secrets` table via migration.
   Run `UPDATE secrets SET org_id = 'org_1'` as a default for existing records.
2. Change `AgentStore.setSecret(secretRef, value)` to
   `setSecret(orgId, secretRef, value)`.
3. Change `AgentStore.getSecret(secretRef)` to `getSecret(orgId, secretRef)`.
4. Update all call sites: `runtime.ts` model profile secret storage, external
   tool secret storage, compat routes.
5. SQLite queries add `WHERE org_id = ?`.
6. `InMemoryStore` changes `Map<string, string>` to
   `Map<string, Map<string, string>>` keyed on `orgId`.

**Files:**
- `backend/packages/persistence/src/protocols.ts`
- `backend/packages/persistence/src/sqlite-store.ts`
- `backend/packages/persistence/src/store.ts`
- `backend/packages/persistence/src/migrations.ts`
- `backend/apps/api/src/runtime.ts`
- `backend/apps/api/src/routes/compat.ts`

### Item 1.2: Add `org_id` to Settings Table

**Problem:** [`sqlite-store.ts#L621-L635`](../../backend/packages/persistence/src/sqlite-store.ts#L621-L635)
— `settings` table has no `org_id`.

**What to do:**

1. Add `org_id TEXT NOT NULL DEFAULT ''` column to `settings` via migration.
2. Change `AgentStore.setSetting(key, value)` to `setSetting(orgId, key, value)`.
3. Change `AgentStore.getSetting(key)` to `getSetting(orgId, key)`.
4. SQLite queries add `WHERE org_id = ?`.

**Files:** Same as 1.1 plus any settings route if one exists.

### Item 1.3: Add Thread/Org Scoping to `LocalMemoryProvider`

**Problem:** [`provider.ts`](../../backend/packages/memory/src/provider.ts)
— `LocalMemoryProvider` is a flat `Map`. All memory across all threads, orgs,
and users lives in one namespace. Tool descriptions say "scoped to the current
Agent Thread" but nothing enforces this.

**What to do:**

1. Change the internal store from `Map<string, MemoryEntry>` to
   `Map<string, Map<string, MemoryEntry>>` where the outer key is the scope
   identifier (e.g., `{orgId}:{threadId}`).
2. Add a `scope` parameter to `remember`, `recall`, `search`, `forget`.
3. Derive the scope from the `RunContext` at the capability router level.
4. `clear()` takes an optional scope; clears only that scope.
5. Add `clearAll()` for testing only.

**Files:**
- `backend/packages/memory/src/provider.ts`
- `backend/packages/capabilities/src/production-router.ts` (memory tool handlers)

### Item 1.4: Add `org_id` and `actor_user_id` Columns to Child Entities

**Problem:** `AgentMessage`, `AgentTodo`, `AgentApproval`, and
`AgentContextSummary` carry no tenant/user identity. They rely on parent
(thread/run) lookups for isolation.

**What to do for Messages:**

1. Add `org_id TEXT NOT NULL DEFAULT ''` and `actor_user_id TEXT` columns to
   `messages` table via migration. Backfill from parent thread/run where possible.
2. Update `AgentMessageSchema` in `schemas.ts` with optional `org_id` and
   `actor_user_id` (optional for backward compat).
3. `createMessage` populates from the creating request's actor and the thread's
   `org_id`.
4. `listMessages` adds `WHERE org_id = ?` filter.

**What to do for Todos:**

1. Add `org_id TEXT NOT NULL DEFAULT ''` and `actor_user_id TEXT` columns to
   `todos` table.
2. `createTodo` populates from the parent run's `org_id`/`actor_user_id`.
3. `listTodos` adds `WHERE org_id = ?` filter.

**What to do for Approvals:**

1. Add `org_id TEXT NOT NULL DEFAULT ''` to `approvals` table.
2. `createApproval` populates from the parent run's `org_id`.
3. `listApprovals` adds `WHERE org_id = ?` filter.

**What to do for Context Summaries:**

1. `Actor_user_id` column already present. Add `WHERE org_id = ?` to queries.
2. `listContextSummaries` currently filters only on `thread_id`; add org filter.

**Files:**
- `backend/packages/contracts/src/schemas.ts`
- `backend/packages/persistence/src/sqlite-store.ts`
- `backend/packages/persistence/src/store.ts`
- `backend/packages/persistence/src/migrations.ts`

### Item 1.5: Fix `listDocuments` to Filter at Store Level

**Problem:** [`sqlite-store.ts#L510-L519`](../../backend/packages/persistence/src/sqlite-store.ts#L510-L519)
— `listDocuments(kind)` does `SELECT id, payload FROM {table}` with no WHERE
clause. Route code manually filters by `org_id` after fetching all rows.

**What to do:**

1. Change `AgentStore.listDocuments(kind)` to `listDocuments(kind, orgId)`.
2. SQLite implementation adds `WHERE org_id = ?` for tables that have the column.
3. `InMemoryStore` filters on `(entry as any).org_id === orgId`.
4. Update all call sites in `runtime.ts`, `compat.ts`, and the skill resolver.

**Files:**
- `backend/packages/persistence/src/protocols.ts`
- `backend/packages/persistence/src/sqlite-store.ts`
- `backend/packages/persistence/src/store.ts`
- `backend/packages/skills/src/resolver.ts`
- `backend/apps/api/src/runtime.ts`
- `backend/apps/api/src/routes/compat.ts`

---

## Phase 2 — API Route Enforcement (P1)

Every API route that returns or mutates user-owned resources must verify that
the authenticated actor matches the resource's owner.

### Item 2.1: Thread Route Actor Checks

**Problem:** [`threads.ts`](../../backend/apps/api/src/routes/threads.ts)
— `GET /api/threads/:id` and `PATCH /api/threads/:id` do not verify
`owner_user_id`.

**What to do:**

1. In `GET /api/threads/:id`, after fetching the thread, verify
   `thread.owner_user_id === actor.userId` (or platform auth scope check).
   Return 403 if mismatch.
2. Same for `PATCH`.
3. `POST /api/threads/:id/messages` — verify the thread belongs to the actor.
4. `GET /api/threads/:id/messages` — verify the thread belongs to the actor.

**Files:** `backend/apps/api/src/routes/threads.ts`

### Item 2.2: Run Route Actor Checks

**Problem:** [`runs.ts`](../../backend/apps/api/src/routes/runs.ts)
— `GET /api/runs/:id`, `POST /api/runs/:id/cancel`, and all
`/api/runs/:id/{stream,events,files,trace,snapshot}` routes do not verify
`actor_user_id`.

**What to do:**

1. Add a helper `assertRunAccess(run, actor)` that checks
   `run.actor_user_id === actor.userId || actor.scopes.includes('*')`.
2. Call it in every run detail route.
3. `POST /api/runs/:id/cancel` additionally checks that the canceling user is the
   run's actor (or has admin scope).

**Files:** `backend/apps/api/src/routes/runs.ts`

### Item 2.3: Approval Route Actor Checks

**Problem:** [`approvals.ts`](../../backend/apps/api/src/routes/approvals.ts)
— `POST /api/approvals/:id/resolve` lets any authenticated user resolve any
approval.

**What to do:**

1. After fetching the approval, fetch its parent run.
2. Verify `run.actor_user_id === actor.userId`.
3. Return 403 if mismatch.

**Files:** `backend/apps/api/src/routes/approvals.ts`

### Item 2.4: Compat Route Actor Checks (Full Sweep)

**Problem:** [`compat.ts`](../../backend/apps/api/src/routes/compat.ts)
— The compat routes for model profiles, skills, external tools, subagent specs,
workspace files, and memory all use only org-level filtering with no user-level
ownership checks.

**What to do:**

1. **Model profiles** (`#L1450-L1503`): Add `owner_user_id` to the profile
   schema. `POST` sets it from the actor. `PATCH`/`enable`/`disable` check
   ownership.
2. **Skills registry** (`#L1505-L1583`): `saveSkillRegistryEntry` and
   `enable`/`disable` check that the entry's `owner_user_id` matches the actor.
3. **User skills** (`#L1524-L1563`): Already scoped by `{orgId}:{actor}:{key}`;
   verify the actor from the token matches the `actor` in the document id.
4. **External tools** (`#L1614-L1670`): Add `owner_user_id`. `POST` sets it.
   `PATCH`/`enable`/`disable`/`reset-cache` check ownership. Remove hardcoded
   `"user_1"`.
5. **Subagent specs** (`#L1584-L1612`): Add `owner_user_id`. Check on
   create/read/update.
6. **Memory entries** (`#L1362-L1448`): Add `owner_user_id`. Check on
   create/delete.
7. **Workspace files** (`#L1672-L1787`): Derive `org_id` from the parent thread
   or run associated with the `workspace_id`. At minimum, check that the
   requesting actor's org matches.

**Files:** `backend/apps/api/src/routes/compat.ts`

### Item 2.5: Document-Level `owner_user_id` Enforcement

**Problem:** Documents (model profiles, skill registry entries, external tool
configs, subagent specs, memory) are stored with `org_id` and `owner_user_id`
columns but individual write operations (`upsertDocument`, `insertDocument`) do
not enforce ownership at the store level.

**What to do:**

1. Add optional `ownerUserId` parameter to `updateDocument`/`deleteDocument`
   on `AgentStore`.
2. SQLite implementations add `AND owner_user_id = ?` to UPDATE/DELETE where
   clauses when the parameter is provided.
3. Route handlers pass the actor's userId.

**Files:**
- `backend/packages/persistence/src/protocols.ts`
- `backend/packages/persistence/src/sqlite-store.ts`
- `backend/packages/persistence/src/store.ts`

---

## Phase 3 — Runtime & Capability Boundary (P1–P2)

### Item 3.1: Add Actor Identity to `RunContext`

**Problem:** [`policy.ts#L4-L6`](../../backend/packages/capabilities/src/policy.ts#L4-L6)
— `RunContext` carries only `run: AgentRun`. The capability router cannot make
user-level authorization decisions.

**What to do:**

1. Extend `RunContext` with `actor: { userId: string; orgId: string; scopes: string[] }`.
2. `PolicyEngine` receives `RunContext` instead of just `AgentRun`.
3. `CapabilityRouter.prepareToolCall` and `executeToolCall` receive the
   enriched context.
4. The call site in `RunLoop.executeToolCall` passes the actor from the run's
   `actor_user_id` (since the run loop runs server-side, it uses the run's own
   actor identity).
5. The call site in `approval-resolution.ts` passes the actor from the run.

**Files:**
- `backend/packages/capabilities/src/policy.ts`
- `backend/packages/capabilities/src/router.ts`
- `backend/packages/capabilities/src/production-router.ts`
- `backend/packages/harness/src/run-loop.ts`
- `backend/apps/api/src/approval-resolution.ts`

### Item 3.2: Scope Active Runs by Org

**Problem:** [`runtime.ts#L357`](../../backend/apps/api/src/runtime.ts#L357)
— `activeRuns` is a global `Map`. Any user can cancel any run.

**What to do:**

1. Change `activeRuns` from `Map<string, ...>` to `Map<string, Map<string, ...>>`
   where the outer key is `orgId`.
2. `cancelRun` accepts `orgId` and scopes cancellation to the org.
3. `scheduleRunExecution` keys by org.

**Files:** `backend/apps/api/src/runtime.ts`

### Item 3.3: Key ProductionCapabilityRouter's Memory Provider by Org/Thread

**Problem:** The `LocalMemoryProvider` instance is shared across all runs.

**What to do:**

1. After Item 1.3 makes `LocalMemoryProvider` scope-aware, the capability router
   passes the run's `org_id` + `thread_id` as the scope when calling memory
   operations.
2. `memory.remember`, `memory.recall`, `memory.search`, `memory.forget` tools all
   derive scope from `RunContext.run.org_id` + `RunContext.run.thread_id`.

**Files:**
- `backend/packages/capabilities/src/production-router.ts`
- `backend/packages/memory/src/provider.ts`

### Item 3.4: Workspace File Org Binding

**Problem:** [`workspace-files.ts`](../../backend/packages/persistence/src/workspace-files.ts)
— Workspace files are organized by `workspace_id` only, with no org/user
binding.

**What to do:**

1. Add a `workspace_meta` table or in-memory map: `{ workspace_id, org_id, thread_id }`.
2. When `workspaceIdForThread` creates a workspace id, also record the binding.
3. `FileWorkspaceStore` methods accept `orgId` and verify the workspace belongs
   to it before any read/write.
4. API routes derive `orgId` from the platform actor and pass it through.

**Files:**
- `backend/packages/persistence/src/workspace-files.ts`
- `backend/packages/persistence/src/sqlite-store.ts` (+ migration)
- `backend/apps/api/src/routes/runs.ts`
- `backend/apps/api/src/routes/compat.ts`

---

## Phase 4 — Verification & Testing

### Item 4.1: Unit Tests for Store-Level Isolation

- `InMemoryStore` tests: verify that `getSecret`/`setSecret` are org-isolated.
- `InMemoryStore` tests: verify that `getSetting`/`setSetting` are org-isolated.
- `InMemoryStore` tests: verify that `listDocuments(kind, orgId)` returns only
  that org's documents.
- `LocalMemoryProvider` tests: verify that `remember`/`recall` are scoped.

### Item 4.2: Integration Tests for Route-Level Enforcement

- Test that `GET /api/threads/:id` returns 403 when `owner_user_id` doesn't
  match the actor.
- Test that `POST /api/runs/:id/cancel` returns 403 for a different user.
- Test that `POST /api/approvals/:id/resolve` returns 403 for wrong actor.
- Test that `PATCH /api/model-profiles/:id` returns 403 for non-owner.
- Test that model profile listing shows only the requesting org's profiles.

### Item 4.3: Cross-Org Isolation Smoke Tests

- Create thread in org A, verify org B cannot see it.
- Create run in org A, verify org B cannot stream/cancel/read it.
- Store secret in org A, verify org B cannot retrieve it.
- Write workspace file in org A, verify org B cannot read it.
- Store memory entry in org A's thread, verify org B cannot recall it.

### Item 4.4: Verification Commands

After all phases, run:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

---

## Dependency Order

```
Phase 1 (Storage Schema)
  ├── 1.1 Secrets org_id        ──┐
  ├── 1.2 Settings org_id       ──┤  independent, can run in parallel
  ├── 1.3 Memory scoping        ──┘
  ├── 1.4 Child entity columns  ─── depends on 1.1/1.2 (migration pattern)
  └── 1.5 listDocuments filter  ─── depends on 1.1/1.2 for column existence

Phase 2 (API Routes)
  ├── 2.1 Thread routes         ──┐
  ├── 2.2 Run routes            ──┤  independent, can run in parallel
  ├── 2.3 Approval routes       ──┘
  ├── 2.4 Compat routes         ─── depends on 2.1, 2.2, 2.3 + Phase 1
  └── 2.5 Document ownership    ─── depends on 2.4

Phase 3 (Runtime)
  ├── 3.1 RunContext actor      ──┐
  ├── 3.2 activeRuns scoping    ──┤  independent
  ├── 3.3 Memory provider       ─── depends on 1.3, 3.1
  └── 3.4 Workspace binding     ─── can start independently

Phase 4 (Testing)
  └── 4.1-4.3                   ─── depends on all of Phase 1-3
```

---

## Out of Scope

The following are explicitly excluded from this phase:

- **Org-to-org sharing models** — resource sharing between orgs (e.g.,
  cross-org skill packages, shared model profiles) is a separate feature.
- **Role-based access control (RBAC) within an org** — the current isolation
  model treats all users in an org as equal owners of their own resources.
  Admin/editor/viewer roles are out of scope.
- **Per-org runtime process isolation** — the runtime remains a singleton.
  Process-level sandboxing is a future concern.
- **Billing / quota enforcement** — per-org or per-user usage quotas belong to
  the platform layer, not the harness.
- **Audit log** — the existing capability audit projection is sufficient for
  now; a full audit trail for admin operations is deferred.
