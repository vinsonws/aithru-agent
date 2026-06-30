# Final Review Fix Report

## What I fixed

1. Draft HTML previews no longer execute scripts before approval/persistence.
   - Changed `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx` so `srcDoc` HTML drafts render in an iframe with `sandbox=""`.
   - Kept the existing persisted-HTML URL iframe path script-enabled (`sandbox="allow-scripts"`).

2. OpenAI Chat Completions tool input stream ids are now unique per model turn.
   - Added optional `turnIndex?: number` to `AgentModelTurnInput`.
   - Passed `turnIndex: turn` from `ModelTurnLoop`.
   - Changed chat stream ids from `chat:${index}` to `chat:${input.turnIndex ?? 0}:${index}` so deltas and final tool calls stay bound within one turn.

3. File-bearing queries now refresh when `workspace.write_file` completes, even before terminal run state.
   - Added a focused helper in `frontend/src/features/chat/useRunStream.ts` to detect newly completed `workspace.write_file` calls.
   - Invalidates `["runs", runId, "snapshot", "files"]` and `["workspaces"]` once per newly completed write-file tool call.
   - Kept the existing terminal run invalidation for `["threads"]` and `["runs"]`.

## TDD evidence

### RED

- Backend:
  - Command: `cd backend && npm run test -- tests/model/sdk-adapters.test.ts`
  - Result: failed as expected with 3 failures.
  - Why expected:
    - chat stream ids were still `chat:0` instead of turn-scoped ids,
    - delta/final tool-call ids were not turn-qualified,
    - two model turns with tool index `0` still collided.

- Frontend:
  - Command: `cd frontend && npm test -- tests/file-preview-drafts.test.mjs tests/use-run-stream.test.mjs`
  - Result: failed as expected with 2 failures.
  - Why expected:
    - draft HTML preview still used `sandbox="allow-scripts"`,
    - `collectRunFileInvalidationKeys` did not exist yet, so pre-terminal file refresh behavior was missing.

### GREEN

- Backend:
  - Command: `cd backend && npm run test -- tests/model/sdk-adapters.test.ts`
  - Result: passed (`14` tests).

- Frontend:
  - Command: `cd frontend && npm test -- tests/file-preview-drafts.test.mjs tests/use-run-stream.test.mjs`
  - Result: passed (`193` tests via the frontend test script).

## Verification commands and results

### Required focused verification

- `cd backend && npm run typecheck`
  - Passed.
- `cd backend && npm run test -- tests/model/sdk-adapters.test.ts`
  - Passed (`14` tests).
- `cd frontend && npm run typecheck`
  - Passed.
- `cd frontend && npm test -- tests/file-preview-drafts.test.mjs tests/use-run-stream.test.mjs`
  - Passed (`193` tests via the frontend test script).

### Additional verification run

- `cd backend && npm run test`
  - Passed (`36` files, `228` tests).
- `cd backend && npm run check:no-python-backend`
  - Passed.
- `cd backend && npm run examples:file-report`
  - Passed.
- `cd frontend && npm test`
  - Passed (`193` tests).

## Files changed

- `backend/packages/model/src/types.ts`
- `backend/packages/harness/src/model-turn.ts`
- `backend/packages/model/src/sdk-adapters.ts`
- `backend/tests/model/sdk-adapters.test.ts`
- `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx`
- `frontend/src/features/chat/useRunStream.ts`
- `frontend/tests/file-preview-drafts.test.mjs`
- `frontend/tests/use-run-stream.test.mjs`
- `.superpowers/sdd/final-review-fix-report.md`

## Self-review findings

- No blocking follow-up found in the allowed edit scope.
- The file refresh invalidation is intentionally narrow:
  - it only reacts to newly completed `workspace.write_file` tool calls,
  - it runs once per new completion sequence,
  - it leaves the existing terminal run refresh behavior unchanged.
- The HTML preview fix is limited to unapproved draft `srcDoc` rendering; persisted file previews keep their prior behavior.

## Concerns

- `useRunStream` does not have `workspaceId`, so the refresh target uses the `["workspaces"]` prefix rather than a narrower workspace-specific key. That matches the requested fallback and keeps the diff inside the allowed file scope.
