# Task 2 Report: Frontend Tool Input Draft State

## Result

Implemented Task 2 only in the frontend reducer/state layer:

- Added exported `ToolInputDraft`.
- Added `RunStreamState.toolInputDrafts` and initialized it to `[]`.
- Added reducer projection for `tool.input_delta`.
- Bound streamed draft entries to `tool.proposed` and terminal tool lifecycle events by `input_stream_id` / `tool_call_id`.

No backend files were changed. No draft file projection or preview panel wiring was added.

## TDD Evidence

### RED

Wrote the failing reducer test first in `frontend/tests/use-run-stream.test.mjs`:

- Added `toolInputDrafts: []` to the local `state()` helper.
- Added `reduceEvent accumulates and binds streamed tool input drafts`.

Focused test command from the brief failed before implementation:

- Command: `cd frontend && npm test -- tests/use-run-stream.test.mjs`
- Failure:
  - `✖ reduceEvent accumulates and binds streamed tool input drafts`
  - `AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal`
  - `+ actual - expected`
  - `+ undefined`
  - expected projected `toolInputDrafts` entry

### GREEN

After the reducer/state changes, the same focused command passed:

- Command: `cd frontend && npm test -- tests/use-run-stream.test.mjs`
- Result:
  - `✔ reduceEvent accumulates and binds streamed tool input drafts`
  - `ℹ pass 183`
  - `ℹ fail 0`

## Files Changed

- `frontend/src/features/chat/useRunStream.ts`
- `frontend/tests/use-run-stream.test.mjs`

## Verification

Passed:

- `cd frontend && npm test -- tests/use-run-stream.test.mjs`

## Self-Review

- The implementation follows the brief’s reducer-only scope and leaves preview/file projection for later tasks.
- I used the existing local reducer/tool lifecycle pattern in `useRunStream.ts`; no helper renames were needed.
- `bindToolInputDraft(...)` only mutates existing draft entries, so non-streamed tool calls remain unchanged.
- `applyToolInputDelta(...)` ignores malformed `index` payloads without widening behavior beyond the brief.

## Concerns

None.
