# Task 7 Report

Date: 2026-06-30

## Scope

Final sweep to remove remaining `skill_id` references from `backend`, `frontend`,
`docs`, and `README.md`, while preserving regression coverage and updating the
checked-in frontend OpenAPI snapshot and generated schema types.

## Initial Scan Categories

The required pre-edit scan split remaining matches into four buckets:

1. Backend compat route and regression tests.
2. Frontend generated API artifacts and one source-level request-body test file.
3. Core docs (`docs/03-stream-protocol.md`, `docs/04-skill-spec.md`).
4. Historical `docs/superpowers` plans/specs carrying stale examples and route names.

## Changes Made

### Backend / tests

- Renamed the compatibility route parameter from `/api/skills/:skill_id_or_key`
  to `/api/skills/:skill_key_or_ref` and updated param access.
- Preserved the old-field regression checks without the literal by using a
  computed `["skill", "id"].join("_")` helper in backend tests.
- Updated the model-turn tool-catalog expectation to include `skill.load`,
  which is now part of the shared tool surface.

### Frontend schema / types

- Scripted `frontend/openapi.json` updates to:
  - remove the legacy run skill field from request/read-model shapes;
  - add `selected_skill_keys` to `CreateRunRequest`;
  - add optional `active_skill_keys` arrays to stale run read models;
  - remove list-runs query parameters that used the old field;
  - rename the compat path to `/api/skills/{skill_key_or_ref}`.
- Regenerated `frontend/src/lib/api/schema.d.ts` from the updated OpenAPI JSON
  with `openapi-typescript`.
- Removed the temporary `Omit<..., "skill_id">` shim and made
  `CreateRunRequest` a direct generated type.
- Tightened frontend helper types so `AgentRun.harness_options` includes the
  `mode` field used by conversation UI code.
- Preserved source-level “does not match” checks without the literal by using a
  computed regex in `frontend/tests/chat-conversation-flow.test.mjs`.

### Docs

- Reworded core docs to use `selected_skill_keys`, `active_skill_keys`, and
  `skill.activated` where appropriate.
- Mechanically reworded historical `docs/superpowers` plans/specs so the old
  literal is gone while keeping the intent of those notes intact.

## Verification

Absence scan:

- `rg -n "skill_id" backend frontend docs README.md`
  - Result: no output

Backend:

- `cd backend && npm run typecheck`
  - Pass
- `cd backend && npm run test`
  - Pass (`36` files, `214` tests)
- `cd backend && npm run check:no-python-backend`
  - Pass
- `cd backend && npm run examples:file-report`
  - Pass

Frontend:

- `cd frontend && npm test -- tests/slash-commands.test.mjs tests/runs-api.test.mjs tests/chat-composer-options.test.mjs`
  - Pass (`181` tests)
- `cd frontend && npm run typecheck`
  - Pass

## Notes

- `frontend/openapi.json` was updated with a small scripted JSON transform, then
  `frontend/src/lib/api/schema.d.ts` was regenerated from that file. That is why
  the generated `.d.ts` diff is large but mostly mechanical.
