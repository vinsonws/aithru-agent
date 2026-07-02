Task 3 Report: Runtime Resolver And Legacy Profile Migration

Summary
- Replaced runtime `model_profile_key` resolution with provider/model `model_ref` resolution.
- Added one-time legacy `model_profile_entry` migration on `GET /api/model-providers`, scoped to the current owner.
- Removed the obsolete model profile registry export and test.
- Updated runtime-adjacent tests to use `model_ref`.

Files Changed
- `backend/apps/api/src/runtime.ts`
- `backend/apps/api/src/routes/model-config.ts`
- `backend/packages/contracts/src/schemas.ts`
- `backend/packages/model/src/index.ts`
- deleted `backend/packages/model/src/profiles.ts`
- `backend/tests/api/route-access.test.ts`
- `backend/tests/integration/api-compat.test.ts`
- `backend/tests/integration/api.test.ts`
- deleted `backend/tests/model/profiles.test.ts`
- `backend/tests/model/skill-load-tool.test.ts`

What Changed

1. Runtime resolver
- Added `modelRefForRun()` and `parseModelRef()`.
- Replaced profile lookup with owner-scoped provider/model document lookup.
- Runtime now emits:
  - `MODEL_NOT_CONFIGURED`
  - `MODEL_PROVIDER_NOT_FOUND`
  - `MODEL_NOT_FOUND`
  - `MODEL_PROVIDER_DISABLED`
  - `MODEL_DISABLED`
  - `MODEL_PROVIDER_SECRET_MISSING`
- `test` providers still use `defaultTestAdapter()`.
- Non-test providers now build SDK adapters from provider kind, provider secret, provider metadata, provider base URL/compat, and model request/provider model id.
- Removed the old scheduler shortcut that skipped execution when `model_profile_key` was absent, so the new resolver is authoritative.

2. Model config migration
- Added `migrateLegacyModelProfilesForRequest()` to `model-config.ts`.
- Added helper functions:
  - `stripKnownModelPrefix()`
  - `slugifyKey()`
  - `humanizeName()`
- Migration runs only from `GET /api/model-providers`.
- Migration is owner-scoped and no-ops if that owner already has any `model_provider_entry` docs.
- Migrated legacy profiles into:
  - `model_provider_entry`
  - `model_entry`

3. Model storage alignment
- Updated model-config route storage to persist `model_entry.key` as the plain model key, while default settings still store full `provider/model` refs.
- Kept API responses using model refs for defaults and plain keys for nested model resources.

4. Contract and cleanup
- Removed transitional `model_profile_key` from `AgentRunHarnessOptionsSchema`.
- Removed the obsolete `profiles.ts` export from `@aithru-agent/model`.
- Deleted the dead profile registry source and test.

5. Tests
- Replaced compat runtime tests to use provider/model refs.
- Added owner-isolation coverage for runtime model resolution.
- Added owner-scoped migration coverage in route access tests.
- Updated other runtime-adjacent tests that still referenced `model_profile_key` so typecheck passes after schema cleanup.
- Adjusted the cancel-shape compat test to avoid racing the immediate test adapter by cancelling a queued stored run directly.

Verification
- `cd backend && npm run test -- tests/integration/api-compat.test.ts tests/api/route-access.test.ts`
  - PASS
- `cd backend && npm run typecheck`
  - PASS

Notes / Concerns
- I updated two extra backend test files outside the original narrow list:
  - `backend/tests/integration/api.test.ts`
  - `backend/tests/model/skill-load-tool.test.ts`
  This was needed to keep `typecheck` green after removing `model_profile_key` from the shared harness options schema.
