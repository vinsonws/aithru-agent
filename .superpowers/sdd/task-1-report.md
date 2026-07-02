Status: DONE_WITH_CONCERNS

Task: Contracts And Persistence for provider/model configuration
Date: 2026-07-02

Scope completed:
- Updated `backend/packages/contracts/src/schemas.ts`
  - Added `AgentModelProviderKind`, `AgentModelCompatKind`, `AgentModelSecretStatusSchema`, `ModelSecretInputSchema`, `AgentModelCapabilitiesSchema`
  - Added `AgentModelProviderEntrySchema`, `AgentModelEntrySchema`, `AgentModelProviderWithModelsSchema`, `AgentModelDefaultSelectionSchema`
  - Added `CreateModelProviderRequestSchema`, `UpdateModelProviderRequestSchema`, `CreateModelRequestSchema`, `UpdateModelRequestSchema`, `UpdateModelDefaultRequestSchema`
  - Replaced `AgentRunHarnessOptionsSchema.model_profile_key` with `model_ref`
- Updated `backend/packages/contracts/src/types.ts`
  - Exported static types for all new provider/model schemas, including `ModelSecretInput`
- Updated `backend/packages/persistence/src/migrations.ts`
  - Added dedicated `model_providers` and `model_entries` tables
  - Added `idx_model_providers_org_key` and `idx_model_entries_org_key`
- Updated `backend/packages/persistence/src/sqlite-store.ts`
  - Mapped `model_provider_entry` -> `model_providers`
  - Mapped `model_entry` -> `model_entries`
- Updated `backend/tests/persistence/sqlite-store.test.ts`
  - Added the required failing-first persistence coverage for provider/model document kinds and dedicated tables

Red/green notes:
- RED: `npm run test -- tests/persistence/sqlite-store.test.ts` failed because `model_provider_entry` and `model_entry` were still falling through the volatile-document path.
- GREEN: the same targeted test passed after adding the table migrations and `DOCUMENT_TABLES` mappings.

Verification run:
- `cd backend && npm run test -- tests/persistence/sqlite-store.test.ts` -> PASS
- `cd backend && npm run test` -> PASS
- `cd backend && npm run check:no-python-backend` -> PASS
- `cd backend && npm run examples:file-report` -> PASS
- `cd backend && npm run typecheck` -> FAIL

Typecheck concern:
- Expected fallout from Task 1 schema ownership: untouched later-task tests still construct `harness_options` with `model_profile_key`, which no longer exists on `AgentRunHarnessOptions`.
- Current errors were in:
  - `backend/tests/integration/api.test.ts`
  - `backend/tests/model/skill-load-tool.test.ts`
- I did not modify those files because Task 1 owns only contracts/persistence plus `backend/tests/persistence/sqlite-store.test.ts`, and the brief explicitly says later tasks will update remaining tests that still rely on `model_profile_key`.

Security/boundary check:
- No provider API keys were stored on model records.
- No raw API keys were added to responses, logs, events, or persisted public payloads.
- No Python backend dependency, workflow behavior, fallback routing, marketplace, or auto-discovery behavior was added.

Git discipline:
- Checked `git status --short` before staging.
- Will stage only:
  - `backend/packages/contracts/src/schemas.ts`
  - `backend/packages/contracts/src/types.ts`
  - `backend/packages/persistence/src/migrations.ts`
  - `backend/packages/persistence/src/sqlite-store.ts`
  - `backend/tests/persistence/sqlite-store.test.ts`
- Left unrelated dirty files untouched.

---

Follow-up fix: transitional `model_profile_key` restored in `AgentRunHarnessOptionsSchema`
Date: 2026-07-02

Reason:
- The Task 1 brief and plan were corrected to keep `model_profile_key` alongside `model_ref` until Task 3 removes runtime profile support.
- This keeps backend typecheck passing between tasks while runtime and test call sites are still migrating.

Change made:
- Updated `backend/packages/contracts/src/schemas.ts`
  - Restored `model_profile_key: Type.Optional(Type.Union([Type.String(), Type.Null()]))`
  - Kept `model_ref` in place

Verification run:
- `cd backend && npm run typecheck` -> PASS
- `cd backend && npm run test -- tests/persistence/sqlite-store.test.ts` -> PASS

Git discipline for follow-up:
- Checked `git status --short` before staging.
- Will stage only `backend/packages/contracts/src/schemas.ts` for this follow-up commit.
