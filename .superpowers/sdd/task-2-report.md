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
