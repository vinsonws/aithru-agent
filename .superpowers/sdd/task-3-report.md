# Task 3 Report: Load Selected Skills At Run Creation

**Status:** Complete

## Files Changed

- `backend/apps/api/src/routes/runs.ts`
- `backend/apps/api/src/routes/compat.ts`
- `backend/tests/integration/api.test.ts`
- `backend/tests/integration/api-compat.test.ts`

## What Changed

- Added local `selectedSkillKeys(...)` normalization in both run-creation route modules.
- Validated every deduped selected skill key before `runtime.store.createRun(run)`.
- Returned HTTP 400 with `{"error":"Skill not found: <key>"}` on unknown selected skills without persisting a run or writing `run.created`.
- Emitted one `skill.activated` event per unique selected skill after `run.created` and before run scheduling/execution.
- Kept skill state event-backed only; no `selected_skill_keys` field was added to `AgentRun`.
- Preserved `selected_skill_keys: null` compatibility behavior in integration coverage.

## Verification

- `cd backend && npm run test -- tests/integration/api.test.ts tests/integration/api-compat.test.ts`
- `cd backend && npm run typecheck`

Both passed.

## Notes

- Compatibility create-run endpoints now surface the same unknown-skill 400 behavior through the shared create-run path.
- No model-driven skill loading, context injection, or tool policy composition was added here.

## Review Fix Update

**Files touched for coverage only**

- `backend/tests/integration/api.test.ts`
- `backend/tests/integration/api-compat.test.ts`

**Fix summary**

- Added a run-count and `run.created` event-count guard to the main API unknown-skill rejection test so it proves failure happens before persistence.
- Added compat coverage for threaded create-run selected-skill activation and unknown-skill rejection.
- Added compat coverage for unknown-skill rejection on both stream create-run paths.
- Kept the changes in integration tests only; no runtime design changes were made.

**Verification**

- `cd backend && npm run test -- tests/integration/api.test.ts tests/integration/api-compat.test.ts`
- `cd backend && npm run typecheck`

Both passed.

**Concerns**

- None.
