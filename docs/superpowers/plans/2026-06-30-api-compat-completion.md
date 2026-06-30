# API Compatibility Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register every non-artifact operation still advertised by `frontend/openapi.json` on the native TypeScript API, with minimal safe compatibility behavior.

**Architecture:** Keep the existing TypeScript backend as the source of truth. Add a compatibility route module that maps old Python-era paths onto current store-backed data where possible and returns inert empty/stub responses where the TS backend has no product implementation yet. Do not recreate the Python backend.

**Tech Stack:** Fastify 5, TypeScript, TypeBox contracts, Vitest, existing in-memory/SQLite stores.

## Global Constraints

- No Python backend imports, process launches, or shell-outs.
- Real tool actions remain behind the capability router.
- Compatibility endpoints may be inert, but must not execute unsafe side effects.
- No new dependencies.

---

## Interface Inventory

```txt
DELETE /api/long-term-memory/{memory_id}
DELETE /api/memory/{memory_id}
DELETE /api/workspaces/{workspace_id}/files/{path}
GET    /api/approvals
GET    /api/approvals/{approval_id}
GET    /api/external-tools/configs
GET    /api/external-tools/configs/{config_id_or_key}
GET    /api/health
GET    /api/long-term-memory/health
GET    /api/memory
GET    /api/memory-candidates
GET    /api/model-profiles
GET    /api/model-profiles/{profile_id_or_key}
GET    /api/runs
GET    /api/runs/{run_id}
GET    /api/runs/{run_id}/capability-audit
GET    /api/runs/{run_id}/events
GET    /api/runs/{run_id}/export
GET    /api/runs/{run_id}/join
GET    /api/runs/{run_id}/memory-recall
GET    /api/runs/{run_id}/operator-actions/lineage
GET    /api/runs/{run_id}/research/continuation
GET    /api/runs/{run_id}/research/evidence
GET    /api/runs/{run_id}/research/execution
GET    /api/runs/{run_id}/research/lineage
GET    /api/runs/{run_id}/research/review
GET    /api/runs/{run_id}/snapshot
GET    /api/runs/{run_id}/stream
GET    /api/runs/{run_id}/subagents
GET    /api/runs/{run_id}/summary
GET    /api/runs/{run_id}/tools
GET    /api/runs/{run_id}/trace
GET    /api/runs/{run_id}/tree
GET    /api/runs/{run_id}/tree/usage
GET    /api/runs/{run_id}/usage
GET    /api/skill-registry
GET    /api/skill-registry/{entry_id_or_key}
GET    /api/skills
GET    /api/skills/{skill_key_or_ref}
GET    /api/subagents
GET    /api/subagents/{key}
GET    /api/threads
GET    /api/threads/dashboard
GET    /api/threads/{thread_id}
GET    /api/threads/{thread_id}/messages
GET    /api/threads/{thread_id}/runs
GET    /api/threads/{thread_id}/runs/{run_id}
GET    /api/threads/{thread_id}/runs/{run_id}/capability-audit
GET    /api/threads/{thread_id}/runs/{run_id}/events
GET    /api/threads/{thread_id}/runs/{run_id}/export
GET    /api/threads/{thread_id}/runs/{run_id}/join
GET    /api/threads/{thread_id}/runs/{run_id}/memory-recall
GET    /api/threads/{thread_id}/runs/{run_id}/operator-actions/lineage
GET    /api/threads/{thread_id}/runs/{run_id}/research/continuation
GET    /api/threads/{thread_id}/runs/{run_id}/research/evidence
GET    /api/threads/{thread_id}/runs/{run_id}/research/execution
GET    /api/threads/{thread_id}/runs/{run_id}/research/lineage
GET    /api/threads/{thread_id}/runs/{run_id}/research/review
GET    /api/threads/{thread_id}/runs/{run_id}/stream
GET    /api/threads/{thread_id}/runs/{run_id}/summary
GET    /api/threads/{thread_id}/runs/{run_id}/tree
GET    /api/threads/{thread_id}/runs/{run_id}/tree/usage
GET    /api/threads/{thread_id}/runs/{run_id}/usage
GET    /api/threads/{thread_id}/summary
GET    /api/threads/{thread_id}/workbench
GET    /api/workspaces/{workspace_id}/diff
GET    /api/workspaces/{workspace_id}/files
GET    /api/workspaces/{workspace_id}/files/{path}
GET    /api/workspaces/{workspace_id}/files/{path}/versions
GET    /api/workspaces/{workspace_id}/images/{path}/view
GET    /api/workspaces/{workspace_id}/snapshot
PATCH  /api/external-tools/configs/{config_id_or_key}
PATCH  /api/model-profiles/{profile_id_or_key}
PATCH  /api/skill-registry/user/{skill_key}
PATCH  /api/skill-registry/{entry_id_or_key}
PATCH  /api/threads/{thread_id}
POST   /api/approvals/{approval_id}/resolve
POST   /api/external-tools/configs
POST   /api/external-tools/configs/{config_id_or_key}/disable
POST   /api/external-tools/configs/{config_id_or_key}/enable
POST   /api/external-tools/configs/{config_id_or_key}/reset-cache
POST   /api/memory
POST   /api/memory-candidates/{candidate_id}/approve
POST   /api/memory-candidates/{candidate_id}/reject
POST   /api/model-profiles
POST   /api/model-profiles/{profile_id_or_key}/disable
POST   /api/model-profiles/{profile_id_or_key}/enable
POST   /api/runs
POST   /api/runs/stream
POST   /api/runs/wait
POST   /api/runs/{run_id}/cancel
POST   /api/runs/{run_id}/external-approval/resolve
POST   /api/runs/{run_id}/external-run/resolve
POST   /api/runs/{run_id}/input
POST   /api/runs/{run_id}/operator-actions/follow-up
POST   /api/runs/{run_id}/research/continue
POST   /api/runs/{run_id}/resume
POST   /api/skill-registry
POST   /api/skill-registry/user
POST   /api/skill-registry/{entry_id_or_key}/disable
POST   /api/skill-registry/{entry_id_or_key}/enable
POST   /api/subagents
POST   /api/threads
POST   /api/threads/{thread_id}/messages
POST   /api/threads/{thread_id}/runs
POST   /api/threads/{thread_id}/runs/stream
POST   /api/threads/{thread_id}/runs/{run_id}/cancel
POST   /api/threads/{thread_id}/runs/{run_id}/input
POST   /api/threads/{thread_id}/runs/{run_id}/operator-actions/follow-up
POST   /api/threads/{thread_id}/runs/{run_id}/research/continue
POST   /api/workspaces/{workspace_id}/files/{path}/convert
POST   /api/workspaces/{workspace_id}/files/{path}/patch
POST   /api/workspaces/{workspace_id}/files/{path}/promote
POST   /api/workspaces/{workspace_id}/restore
POST   /api/workspaces/{workspace_id}/uploads
PUT    /api/workspaces/{workspace_id}/files/{path}
```

## Tasks

### Task 1: Route Coverage Test

**Files:**
- Create: `backend/tests/integration/api-compat.test.ts`

**Interfaces:**
- Consumes: `frontend/openapi.json`, `createApp()`.
- Produces: failing route coverage check for every operation in the inventory.

- [ ] Write a Vitest test that loads `frontend/openapi.json`, converts `{param}` to Fastify `:param`, skips deleted artifact routes, and compares those operations with `app.printRoutes()`.
- [ ] Run `cd backend && npx vitest run tests/integration/api-compat.test.ts`; expected failure lists the missing operations.

### Task 2: Compatibility Routes

**Files:**
- Create: `backend/apps/api/src/routes/compat.ts`
- Modify: `backend/apps/api/src/app.ts`
- Modify: `backend/apps/api/src/routes/runs.ts`
- Modify: `backend/apps/api/src/routes/approvals.ts`
- Modify: `backend/packages/contracts/src/schemas.ts`

**Interfaces:**
- Consumes: existing runtime store methods.
- Produces: route registration for all OpenAPI operations, store-backed where cheap, inert where not implemented.

- [ ] Add thread aliases: get thread, dashboard, summary, workbench, thread-run list/create/stream/detail aliases.
- [ ] Add run aliases: stream/create/wait, resume/input/cancel aliases, summary/usage/tree/research/export/memory stubs.
- [ ] Add resource endpoints: approvals list/get, memory, skills, subagents, model profiles, external tool configs.
- [ ] Add workspace endpoints: file list/read/write/delete/content-ish metadata, snapshot/diff/uploads/patch/convert/promote/restore.
- [ ] Keep unsafe or unimplemented operations inert and explicit.

### Task 3: Verification

**Files:**
- Existing backend tests and scripts.

**Interfaces:**
- Consumes: repo verification scripts from `AGENTS.md`.
- Produces: fresh verification evidence.

- [ ] Run `cd backend && npx vitest run tests/integration/api-compat.test.ts`.
- [ ] Run `cd backend && npm run typecheck`.
- [ ] Run `cd backend && npm run test`.
- [ ] Run `cd backend && npm run check:no-python-backend`.
- [ ] Run `cd backend && npm run examples:file-report`.
