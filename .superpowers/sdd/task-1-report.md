# Task 1 Report: Remove `skill_id` From Contracts And Persistence

## What I Implemented

- Removed `skill_id` from `AgentRunSchema` and `CreateRunRequestSchema`.
- Added `selected_skill_keys?: string[] | null` to `CreateRunRequestSchema`.
- Set `additionalProperties: false` on both schemas so removed fields fail validation.
- Removed `skill_id` from the SQLite `runs` table DDL, insert path, and hydration.
- Updated run creation paths to accept `selected_skill_keys` and stop emitting `skill_id`.
- Updated run fixtures, examples, and affected skill/runtime tests to use the new field shape.

## Test Commands And Results

- `cd backend && npm run test -- tests/contracts/schemas.test.ts`
  - Passed after implementation.
- `cd backend && npm run test -- tests/persistence/sqlite-store.test.ts -t "stores runs without a skill_id column"`
  - Passed after implementation.
- `cd backend && npm run test -- tests/contracts/schemas.test.ts tests/persistence/sqlite-store.test.ts`
  - Passed.
- `cd backend && npm run typecheck`
  - Passed.

## TDD Evidence

### RED

- `cd backend && npm run test -- tests/contracts/schemas.test.ts`
  - Failed because `AgentRunSchema` still exposed `skill_id` and `CreateRunRequestSchema` still accepted `skill_id`.
- `cd backend && npm run test -- tests/persistence/sqlite-store.test.ts -t "stores runs without a skill_id column"`
  - Failed because `SqliteStore` still persisted/hydrated `skill_id`.

### GREEN

- After the schema and persistence edits, both focused tests passed:
  - `tests/contracts/schemas.test.ts`
  - `tests/persistence/sqlite-store.test.ts`

## Files Changed

- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/packages/contracts/src/schemas.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/packages/persistence/src/migrations.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/packages/persistence/src/sqlite-store.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/apps/api/src/routes/runs.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/apps/api/src/routes/compat.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/packages/capabilities/src/production-router.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/packages/harness/src/model-turn.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/packages/subagents/src/runner.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/examples/approval_demo.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/examples/file_report_agent.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/contracts/schemas.test.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/persistence/sqlite-store.test.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/capability/skill-policy.test.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/model/skill-context.test.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/model/model-turn.test.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/worker/external-run.test.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/integration/api.test.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/integration/api-compat.test.ts`

## Self-Review Findings

- The removed field no longer appears in public run contracts or SQLite persistence.
- Validation now rejects removed properties instead of silently ignoring them.
- The run creation and skill-policy paths now use `selected_skill_keys` where they need a selected skill value.

## Concerns

- I did not run the full backend test suite, only the targeted Task 1 tests plus typecheck.
- Skill selection is still effectively single-key at the runtime decision points I touched; broader multi-skill behavior is deferred to later tasks.

## Follow-up Fix Notes

### Fix summary

- Removed the out-of-scope `selected_skill_keys` runtime state from API-created `AgentRun` objects in `backend/apps/api/src/routes/runs.ts` and `backend/apps/api/src/routes/compat.ts`.
- Removed ad-hoc run-state skill activation from `backend/packages/harness/src/model-turn.ts`; model turns now build context with no skill instructions and `active_skill_key: null`.
- Removed ad-hoc run-state skill policy composition from `backend/packages/capabilities/src/production-router.ts`; router policy no longer derives from `selected_skill_keys` on the run.
- Updated focused runtime tests to verify that Task 1 keeps the request shape change but does not activate skills or policies from run state yet.

### Tests run and results

- `cd backend && npm run test -- tests/model/skill-context.test.ts tests/capability/skill-policy.test.ts`
  - Failed first, confirming the out-of-scope runtime behavior was still active.
- `cd backend && npm run test -- tests/contracts/schemas.test.ts tests/persistence/sqlite-store.test.ts tests/model/skill-context.test.ts tests/capability/skill-policy.test.ts`
  - Passed.
- `cd backend && npm run typecheck`
  - Passed.

### Files changed

- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/apps/api/src/routes/runs.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/apps/api/src/routes/compat.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/packages/harness/src/model-turn.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/packages/capabilities/src/production-router.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/model/skill-context.test.ts`
- `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/capability/skill-policy.test.ts`

### Concerns

- Focused verification passed, but I did not rerun the full backend suite.
- Runtime skill activation and policy still need the later event-driven design from Tasks 2-5; this fix intentionally leaves that work undone.
