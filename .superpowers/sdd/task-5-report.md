# Task 5 Report: Settings UI And Chat Selector

Status: DONE

## Scope completed

Implemented Task 5 exactly against the provider/model backend shape introduced in Task 4:

- migrated the settings Models tab from `modelProfilesApi` to `modelProvidersApi`
- replaced profile-era form helpers with provider/model payload helpers
- moved chat and new-thread model selection to `model_ref`
- kept the explicit no-model state and blocked send until a usable `model_ref` exists
- updated the named source tests from the brief and repaired two brittle source assertions exposed by formatting

## Files changed

### Product code

- `frontend/src/features/admin/modelProfileForm.ts`
- `frontend/src/features/admin/ModelProfilesPage.tsx`
- `frontend/src/features/manager/ManagerDialogs.tsx`
- `frontend/src/features/chat/ReferenceComposerSurface.tsx`
- `frontend/src/features/chat/ChatComposer.tsx`
- `frontend/src/features/conversation/NewThreadPage.tsx`
- `frontend/src/i18n/resources/en/settings.json`
- `frontend/src/i18n/resources/zh/settings.json`
- `frontend/src/i18n/resources/en/chat.json`
- `frontend/src/i18n/resources/zh/chat.json`

### Tests

- `frontend/tests/model-profile-form.test.mjs`
- `frontend/tests/chat-conversation-flow.test.mjs`
- `frontend/tests/settings-tabs.test.mjs`
- `frontend/tests/chat-i18n-usage.test.mjs`
- `frontend/tests/fixtures/model-profile-form.ts`

## What changed

### 1. Provider/model helper module

Replaced the old profile-form helper surface with the Task 5 helpers:

- `slugifyModelKey`
- `deepSeekPresetProvider`
- `deepSeekPresetModels`
- `buildCustomProviderPayload`
- `buildModelPayload`

These now produce the provider-first payloads expected by `modelProvidersApi`.

### 2. Models settings UI

Rebuilt `ModelProfilesContent` into a provider-first operational settings surface while keeping the exported component name stable.

Implemented:

- `useQuery({ queryKey: ["model-providers"], queryFn: modelProvidersApi.list })`
- empty-state / quick-add actions for:
  - `DeepSeek`
  - `OpenAI-compatible`
- DeepSeek creation flow:
  1. `modelProvidersApi.create(deepSeekPresetProvider(apiKey))`
  2. `modelProvidersApi.createModel("deepseek", model)` for both preset models
  3. invalidate `["model-providers"]`
- custom provider flow that creates one provider and multiple models
- provider list showing provider names plus enabled-model counts
- selected provider panel showing provider fields and model rows
- provider enabled toggle via `modelProvidersApi.patch(provider.key, { enabled })`
- model enabled toggle via `modelProvidersApi.patchModel(provider.key, model.key, { enabled })`
- default-model action via `modelProvidersApi.setDefault({ model_ref })`

Not added, per brief:

- connection testing
- marketplace/discovery
- routing changes
- workflow semantics

### 3. Settings labels

Kept stable tab value `profiles`, but renamed the visible settings copy to:

- `models`
- `modelsDescription`

Updated both English and Chinese resources, and updated runtime managed-configuration badges to use the new label.

### 4. Composer and new-thread model selection

Updated the active chat entry points to provider/model selection:

- `ReferenceComposerSurface`
  - replaced `profileKey` with `modelRef`
  - replaced `modelProfiles` with `modelProviders`
  - uses `flattenUsableModels(modelProviders)`
  - groups menu rows by provider name
  - explicit no-model message remains
- `ChatComposer`
  - queries `modelProvidersApi.list`
  - maintains `modelRef` state
  - uses `selectUsableModelRef`
  - blocks send when no usable `modelRef`
  - passes `modelRef` into `buildComposerHarnessOptions`
- `NewThreadPage`
  - same migration as `ChatComposer`

## Verification

### Red step from the brief

Ran:

```bash
cd frontend
npm run test -- tests/model-profile-form.test.mjs tests/chat-conversation-flow.test.mjs
```

Result before implementation: failed as expected against the old profile-era code.

### Final focused frontend checks

Ran:

```bash
cd frontend
npm run test -- tests/model-profile-form.test.mjs tests/chat-conversation-flow.test.mjs tests/settings-tabs.test.mjs tests/composer-state.test.mjs
```

Result: passed.

Ran:

```bash
cd frontend
npm run typecheck
```

Result: passed.

### Extra check that also ran

Because the repo test command expands to `tests/*.test.mjs`, the focused test command also exercised the broader frontend source-test suite. That full invoked set passed as well.

## Self-review: stale active UI profile usage

Checked the active settings/chat surfaces for stale profile-era selection wiring.

Confirmed migrated away from active UI paths:

- `frontend/src/features/admin/ModelProfilesPage.tsx`
- `frontend/src/features/chat/ReferenceComposerSurface.tsx`
- `frontend/src/features/chat/ChatComposer.tsx`
- `frontend/src/features/conversation/NewThreadPage.tsx`
- `frontend/src/features/manager/ManagerDialogs.tsx`
- settings/chat i18n keys used by those surfaces

Remaining `profileKey`/`selectUsableModelProfileKey` references are in `composerState` summary helpers only, not in the active settings/chat selector flow changed by Task 5.

## Dirty-worktree handling

- did not touch unrelated dirty file `scripts/run-mock.sh`
- did not revert or overwrite unrelated user/previous-task work
- integrated with the existing explicit no-model / blocked-send behavior

## Concerns

None.
