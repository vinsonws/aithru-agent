# Task 2 Report: Provider And Model API Routes

Date: 2026-07-02

## Scope

Implemented only Task 2 backend API route work:

- created `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/apps/api/src/routes/model-config.ts`
- updated `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/apps/api/src/app.ts`
- updated `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/apps/api/src/platform-auth.ts`
- added `/Users/vinsonws/code-repo/github.com/vinsonws/aithru-agent/backend/tests/api/model-config-routes.test.ts`

Legacy `/api/model-profiles` behavior was left untouched.

## TDD Flow

1. Added the route test file from the brief exactly.
2. Ran:

```bash
cd backend && npm run test -- tests/api/model-config-routes.test.ts
```

Observed the expected red failure:

- missing module `../../apps/api/src/routes/model-config.js`

3. Implemented the new route module and wiring.
4. Re-ran the focused route test until green.

## What Changed

### `backend/apps/api/src/routes/model-config.ts`

Added:

- `modelRef(providerKey, modelKey)`
- `isValidModelKey(value)`
- provider CRUD routes under `/api/model-providers`
- nested model CRUD routes under `/api/model-providers/:provider_key/models`
- default model routes:
  - `GET /api/model-default`
  - `PUT /api/model-default`

Behavior implemented per brief:

- org-scoped document reads and writes
- actor-owner filtering for authenticated requests
- provider secret writes through `store.setSecret(...)`
- redacted secret status responses only
- provider key and model key validation with `400`
- stored model `key` as `provider/model`
- returned model payloads normalized back to per-provider model keys
- provider delete cascades to child models
- deleting the selected default provider/model clears `model.default_ref` to `""`
- `PUT /api/model-default` validates provider/model existence, ownership, and enabled status

### `backend/apps/api/src/app.ts`

Registered `registerModelConfigRoutes(app)`.

### `backend/apps/api/src/platform-auth.ts`

Classified these as settings routes:

- `/api/model-providers`
- `/api/model-default`

## Verification

Passed:

```bash
cd backend && npm run test -- tests/api/model-config-routes.test.ts
cd backend && npm run typecheck
```

## Notes / Concerns

- I added `/api/model-default` to settings-path auth classification alongside the brief-required `/api/model-providers`, since the new default-model API is the same settings surface and otherwise would have weaker scope mapping.
- The brief required storing model document `key` as `provider/model`, while the API examples and tests expect response `key` values like `echo`. The route stores the full key internally and normalizes it back in responses.

## Review Fix Pass

Reviewer findings confirmed:

- `model.default_ref` was only org-scoped, so same-org different owners with the same `provider/model` names could interfere with each other.
- malformed `provider_key` and `model_key` path params were falling through to `404` instead of returning `400`.

Fixes applied:

- added owner-scoped settings helper behavior so authenticated requests use:
  - `model.default_ref.<owner_user_id>`
  - legacy unauthenticated/local mode still uses `model.default_ref`
- updated `GET /api/model-default` and `PUT /api/model-default` to use the owner-scoped setting key
- updated model delete and provider delete cascade clearing to clear only the current owner's default setting
- added focused tests proving one user's delete does not clear another user's default in the same org
- added focused malformed path-param tests for representative provider/model GET, PATCH, and DELETE paths returning `400`

Verification for the fix pass:

```bash
cd backend && npm run test -- tests/api/model-config-routes.test.ts
cd backend && npm run typecheck
```

Results:

- route test: passed (`6` tests)
- typecheck: passed

## Re-review Fix Pass

Remaining issue confirmed:

- unauthenticated/local mode reads and writes `model.default_ref`, but delete-time clearing only checked the owner-scoped key path, which could leave the legacy local default stale after deleting the selected model.

Fix applied:

- kept authenticated owner-scoped clearing behavior
- updated delete-time default clearing helper to also clear the legacy local `model.default_ref` when it matches the deleted `model_ref`
- added a focused local-mode route test proving `model.default_ref` is cleared when deleting the selected model without an authenticated actor

Verification for the re-review fix pass:

```bash
cd backend && npm run test -- tests/api/model-config-routes.test.ts
cd backend && npm run typecheck
```

Results:

- route test: passed (`7` tests)
- typecheck: passed
