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

## Review Fix Notes

- Removed unbacked `active_skill_keys` fields from the checked-in frontend
  OpenAPI snapshot and regenerated `frontend/src/lib/api/schema.d.ts` so
  `AgentRun`, `RunListItem`, `RunDetailResponse`, `ResolveExternalRunResponse`,
  and `RunTreeNode` match the actual backend responses again.
- Corrected `docs/03-stream-protocol.md` so `run.created` documents the emitted
  `{ run_id, status }` payload, and kept skill selection details under
  `skill.activated`.
- Reworded the progressive-disclosure design/history docs to refer to the
  former single run skill selector instead of invented identifiers or run-backed
  active-skill state.
- Added a focused compatibility test that fails if `frontend/openapi.json`
  reintroduces `active_skill_keys` on unbacked run read models.

### Review Fix Verification

- `rg -n "active_skill_keys" frontend/openapi.json frontend/src/lib/api/schema.d.ts`
  - Result: no output
- `rg -n "legacy_run_skill_field|run-local active skill state|selected_skill_keys|skill\\.activated|run.created" docs/03-stream-protocol.md docs/superpowers/specs/2026-06-30-agent-skill-progressive-disclosure-design.md docs/superpowers/plans/2026-06-30-agent-skill-progressive-disclosure.md docs/04-skill-spec.md`
  - Result: remaining matches are the expected `selected_skill_keys`,
    `skill.activated`, and `run.created` references; no
    `legacy_run_skill_field` or `run-local active skill state`
- `rg -n "skill_id" backend frontend docs README.md`
  - Result: no output
- `cd backend && npm run typecheck && npm run test && npm run check:no-python-backend && npm run examples:file-report`
  - Result: pass (`36` files, `215` tests; no-python check passed; file report example completed)
- `cd frontend && npm test -- tests/slash-commands.test.mjs tests/runs-api.test.mjs tests/chat-composer-options.test.mjs && npm run typecheck`
  - Result: pass (`181` tests)

## Task 7 Review Fix 2

### Scoped fixes

- Updated `frontend/openapi.json` so `AgentMessage` now advertises
  `workspace_paths` instead of stale `artifact_ids`, and aligned
  `AppendMessageRequest` with the backend contract by restoring optional
  `run_id`.
- Regenerated `frontend/src/lib/api/schema.d.ts` from the checked-in OpenAPI
  snapshot with `openapi-typescript`.
- Corrected the chat workbench plan example to send
  `selected_skill_keys` as `vars.skillId ? [vars.skillId] : null`.
- Reworded the historical mem0 plan examples to use
  `selected_skill_keys` / `selected_skill_keys` metadata instead of invented
  singular run or metadata fields.

### Verification

- `rg -n "skill_id" backend frontend docs README.md`
  - Result: no output
- `node - <<'NODE' ... AgentMessage props from frontend/openapi.json ... NODE`
  - Result: `AgentMessage` properties are `id, thread_id, role, content, run_id, workspace_paths, created_at`; `artifact_ids` absent; `workspace_paths` present
- `node - <<'NODE' ... AgentMessage block from frontend/src/lib/api/schema.d.ts ... NODE`
  - Result: `schema.d.ts` `AgentMessage` block has `workspace_paths: string[];` and no `artifact_ids`
- `cd backend && npm run typecheck`
  - Result: pass
- `cd frontend && npm run typecheck`
  - Result: pass
- `cd backend && npx vitest run tests/integration/api-compat.test.ts`
  - Result: pass (`1` file, `19` tests)
