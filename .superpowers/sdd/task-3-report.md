# Task 3 Report: Draft Workspace File Projection

## What I implemented

- Added `buildDraftWorkspaceFiles()` to project `workspace.write_file` tool input drafts into draft workspace file records.
- Added partial JSON extraction helpers so incomplete streamed tool input can still surface `path` and partial `content`.
- Extended `RunFileView` with draft-only fields: `isDraft`, `draftContent`, `draftStatus`, and `draftRevision`.
- Updated `buildRunFileViews()` to include draft workspace files when no real workspace file exists yet, and to suppress the draft once the real file path appears.

## What I tested and test results

- Focused frontend test file: `frontend/tests/run-files-view.test.mjs`
- Result: PASS
- Added coverage for:
  - extracting partial `workspace.write_file` content from streamed tool input
  - showing draft file views before the real workspace file exists
  - preferring the real workspace file view once the file exists

## TDD Evidence

### RED

Command:

```bash
cd frontend
npm test -- tests/run-files-view.test.mjs
```

Observed failing output:

```txt
✖ buildDraftWorkspaceFiles extracts workspace write_file partial content
  TypeError: buildDraftWorkspaceFiles is not a function

✖ buildRunFileViews includes draft files until a real file exists
  AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  0 !== 1
```

Why expected:

- `buildDraftWorkspaceFiles` did not exist yet.
- `buildRunFileViews` ignored `draftWorkspaceFiles`, so the draft-only case returned no views.

### GREEN

Command:

```bash
cd frontend
npm test -- tests/run-files-view.test.mjs
```

Observed passing output:

```txt
✔ buildDraftWorkspaceFiles extracts workspace write_file partial content
✔ buildRunFileViews includes draft files until a real file exists
ℹ pass 185
ℹ fail 0
```

## Files changed

- `frontend/src/features/inspection/runFilesView.ts`
- `frontend/tests/run-files-view.test.mjs`
- `.superpowers/sdd/task-3-report.md`

## Self-review findings

- Kept the change local to the projection layer and reused existing file classification helpers.
- Used a tiny fallback parser for partial JSON instead of adding dependencies or cross-feature coupling.
- Real-file suppression normalizes leading slashes so streamed draft paths and stored workspace paths match.

## Issues or concerns

- Focused test coverage is good for this task, but the draft projection is not yet exercised through the sidebar panels; that belongs to the next task.
