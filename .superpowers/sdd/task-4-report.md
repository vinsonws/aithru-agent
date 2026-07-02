Task 4 Report: Frontend API, Types, And Composer State

Scope completed:
- Updated the static frontend OpenAPI document to advertise provider/model configuration endpoints and `model_ref` on run harness options.
- Regenerated `frontend/src/lib/api/schema.d.ts` from the updated static OpenAPI.
- Added provider/model/default-model type exports in `frontend/src/lib/api/types.ts`.
- Added `modelProvidersApi` helpers in `frontend/src/lib/api/resources.ts`.
- Updated `frontend/src/features/chat/composerState.ts` to:
  - emit `model_ref` from `buildComposerHarnessOptions`
  - add `modelRef`
  - add `flattenUsableModels`
  - add `selectUsableModelRef`
- Updated `frontend/src/features/conversation/runHeaderView.ts` to prefer `harness_options.model_ref`.
- Updated the targeted frontend tests to assert `model_ref` behavior and provider/model flattening.

Files changed:
- `frontend/openapi.json`
- `frontend/src/lib/api/schema.d.ts`
- `frontend/src/lib/api/types.ts`
- `frontend/src/lib/api/resources.ts`
- `frontend/src/features/chat/composerState.ts`
- `frontend/src/features/conversation/runHeaderView.ts`
- `frontend/tests/composer-state.test.mjs`
- `frontend/tests/chat-composer-options.test.mjs`
- `frontend/tests/run-header-view.test.mjs`

Verification:
- Red phase:
  - `cd frontend && npm run test -- tests/composer-state.test.mjs tests/chat-composer-options.test.mjs tests/run-header-view.test.mjs`
  - Failed as expected on missing `model_ref` wiring, missing provider/model flatten helpers, and old run-header label precedence.
- Green phase:
  - `cd frontend && npm run test -- tests/composer-state.test.mjs tests/chat-composer-options.test.mjs tests/run-header-view.test.mjs`
  - Passed.

Notes:
- I kept legacy `modelProfilesApi` and profile type exports in place so untouched settings/chat files in the current worktree do not lose imports before Task 5 switches those surfaces over. Task 4 adds the provider/model frontend surface without ripping out the old one yet.
- I did not modify settings UI files or `ReferenceComposerSurface`, per task scope.
- There are unrelated pre-existing worktree changes outside Task 4 files; they were not staged.

---

Task 4 follow-up fix: remove legacy model_profile_key from frontend run harness contract

Review issue addressed:
- `AgentRunHarnessOptions` in the frontend static OpenAPI and generated schema still exposed `model_profile_key`.
- This follow-up removes that legacy field from the frontend contract while keeping temporary legacy `modelProfilesApi` and `AgentModelProfileEntry` exports untouched for Task 5 migration work.

Files changed in follow-up:
- `frontend/openapi.json`
- `frontend/src/lib/api/schema.d.ts`
- `frontend/tests/composer-state.test.mjs`

Focused regression coverage added:
- `frontend/tests/composer-state.test.mjs`
  - asserts frontend run harness contract still exposes `model_ref`
  - asserts frontend static OpenAPI and generated schema no longer expose `model_profile_key`

Verification output:
- Schema grep:
  - `rg -n "model_profile_key|model_ref\?: string \| null;" frontend/openapi.json frontend/src/lib/api/schema.d.ts`
  - result: only `model_ref?: string | null;` remains in `frontend/src/lib/api/schema.d.ts`; no `model_profile_key` matches in either file
- Targeted tests:
  - `cd frontend && npm run test -- tests/composer-state.test.mjs tests/chat-composer-options.test.mjs tests/run-header-view.test.mjs`
  - result: pass (`217` tests, `0` failures)
