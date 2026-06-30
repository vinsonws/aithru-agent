# Task 4 Report: Draft File UI Wiring

## What I implemented

- Wired `draftWorkspaceFiles` through `AppShell` into both `FileListPanel` and `FilePreviewPanel`.
- Derived draft workspace files from `streamState.toolInputDrafts` with `buildDraftWorkspaceFiles(...)`.
- Added one-shot auto-open behavior in `AppShell` for the first non-empty live draft file, tracked by `openedDraftFileIdsRef`.
- Made `FilePreviewPanel` draft-aware so draft-backed files render from `draftContent` without workspace preview fetches.
- Added inline HTML draft preview rendering via `iframe srcDoc`.

## What I tested and test results

- Focused frontend tests:
  - `frontend/tests/file-preview-drafts.test.mjs`
  - `frontend/tests/app-shell-actions.test.mjs`
  - `frontend/tests/run-files-view.test.mjs`
  - `frontend/tests/use-run-stream.test.mjs`
- Result: PASS

## TDD Evidence

### RED

Command:

```bash
cd frontend
npm test -- tests/file-preview-drafts.test.mjs tests/app-shell-actions.test.mjs
```

Output summary:

```txt
fail 3
- app shell derives draft workspace files and auto-opens them once
- FilePreviewPanel renders draft previews without workspace fetches
- FileListPanel passes draft workspace files into run file views
```

Why expected:

- None of the three target UI files referenced `draftWorkspaceFiles`, `buildDraftWorkspaceFiles`, or the draft-preview fetch guards yet.

### GREEN

Command:

```bash
cd frontend
npm test -- tests/file-preview-drafts.test.mjs tests/app-shell-actions.test.mjs tests/run-files-view.test.mjs tests/use-run-stream.test.mjs
```

Output summary:

```txt
pass 188
fail 0
```

## Files changed

- `frontend/src/AppShell.tsx`
- `frontend/src/features/sidebar/panels/FileListPanel.tsx`
- `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx`
- `frontend/tests/app-shell-actions.test.mjs`
- `frontend/tests/file-preview-drafts.test.mjs`

## Self-review findings

- Kept the change on the existing `buildDraftWorkspaceFiles` / `buildRunFileViews` path instead of adding new state or fetch logic.
- Draft preview fetch suppression only applies when `draftContent` exists, so persisted workspace previews still follow the old path.
- Auto-open is one-shot per draft file id and ignores empty draft bodies to avoid noisy panel churn.

## Issues or concerns

- The focused `npm test -- ...` command still runs the repo's full `tests/*.test.mjs` glob because of the existing frontend test script, but the requested target tests are included and passing.

## Fix follow-up: review findings

### What I fixed

- Scoped draft auto-open tracking by run in `frontend/src/AppShell.tsx` with `draftAutoOpenKey(activeRunId, fileId)`.
- Updated the one-shot auto-open effect to store run-scoped keys instead of raw draft file ids, so the same draft path can auto-open once in each run.

### Added/strengthened tests

- Strengthened `frontend/tests/app-shell-actions.test.mjs` beyond source regex checks:
  - transpiles `AppShell.tsx` with the real TypeScript compiler,
  - extracts the real `draftAutoOpenKey(...)` helper,
  - asserts the same draft file id produces different auto-open keys for different run ids,
  - asserts null run ids do not produce an auto-open key.
- Kept the existing source wiring assertions to verify the effect calls `draftAutoOpenKey(activeRunId, draft.id)`.

### Fix TDD evidence

#### RED

Command:

```bash
cd frontend
npm test -- tests/app-shell-actions.test.mjs tests/file-preview-drafts.test.mjs tests/run-files-view.test.mjs tests/use-run-stream.test.mjs
```

Output summary:

```txt
fail 1
- app shell scopes one-shot draft auto-open keys per run
Expected transpiled AppShell to include draftAutoOpenKey
```

Why expected:

- The code still tracked opened drafts by raw `file.id`, so there was no run-scoped helper for the test to exercise.

#### GREEN

Command:

```bash
cd frontend
npm test -- tests/app-shell-actions.test.mjs tests/file-preview-drafts.test.mjs tests/run-files-view.test.mjs tests/use-run-stream.test.mjs
```

Output summary:

```txt
pass 189
fail 0
```
