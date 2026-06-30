# Task 2 Report: Add Skill Catalog And Activation Projection

## Result

Implemented the task-2 primitives only:

- `SkillResolver.listVisible(orgId, actorUserId)` returns visible catalog metadata without instructions.
- `activeSkillKeysFromEvents(events)` projects ordered unique active skill keys from `skill.activated` events.
- `skillLoadToolDescriptor` and `emitSkillActivated(...)` are available from the harness.
- `skill_id` was not reintroduced anywhere.

## TDD Evidence

### RED

Focused tests failed before implementation for the exact missing APIs:

- `backend/tests/model/skill-activation-state.test.ts`
  - Failed with: `(0 , activeSkillKeysFromEvents) is not a function`
- `backend/tests/skills/loader.test.ts`
  - Failed with: `resolver.listVisible is not a function`

### GREEN

After implementation, the focused tests passed:

- `npm run test -- tests/model/skill-activation-state.test.ts tests/skills/loader.test.ts`

## Files Changed

- `backend/packages/skills/src/resolver.ts`
- `backend/packages/capabilities/src/skill-state.ts`
- `backend/packages/capabilities/src/index.ts`
- `backend/packages/harness/src/skills.ts`
- `backend/packages/harness/src/index.ts`
- `backend/tests/skills/loader.test.ts`
- `backend/tests/model/skill-activation-state.test.ts`

## Verification

Passed:

- `cd backend && npm run test -- tests/model/skill-activation-state.test.ts tests/skills/loader.test.ts`
- `cd backend && npm run typecheck`
- `cd backend && npm run test`
- `cd backend && npm run check:no-python-backend`
- `cd backend && npm run examples:file-report`

## Self-Review

- Catalog projection stays metadata-only and does not expose instructions.
- Capability code remains independent; `activeSkillKeysFromEvents` lives in `capabilities`.
- No model-turn runtime behavior, API run creation, or capability policy changes were added.

## Concerns

None.
