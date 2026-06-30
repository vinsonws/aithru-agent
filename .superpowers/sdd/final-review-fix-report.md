# Final Review Fix Report

## What changed

### 1. Route `skill.load` through the capability boundary and shared tool lifecycle

- Moved `skill.load` onto the production capability surface in `backend/packages/capabilities/src/production-router.ts`.
- Added low-risk descriptor metadata so `skill.load` is listed by `CapabilityRouter.listTools()` like other tools.
- Implemented `skill.load` execution inside `ProductionCapabilityRouter.executeToolCall()`:
  - validates `key`,
  - resolves only visible skills through `SkillResolver`,
  - reuses active-skill event state to avoid duplicate activation,
  - emits `skill.activated` during capability execution with a policy snapshot,
  - returns structured tool success/error results.
- Removed the `ModelTurnLoop` interception in `backend/packages/harness/src/model-turn.ts`, so model-requested `skill.load` now flows through `RunLoop.executeToolCall()` and emits the normal `tool.proposed` / `tool.started` / `tool.completed` or `tool.failed` events.
- Removed the now-dead harness-local `skill.load` descriptor stub from `backend/packages/harness/src/skills.ts`.

### 2. Derive effective skill policy from activation event snapshots

- Added `skillPolicySnapshotsFromEvents()` in `backend/packages/capabilities/src/skill-state.ts`.
- Changed `ProductionCapabilityRouter.skillPolicyForRun()` to build policy from `skill.activated` payload snapshots instead of re-resolving current registry state.
- Malformed `skill.activated` policy payloads now fail closed by returning a deny-all effective policy.
- Added focused tests proving policy remains enforced from the activation snapshot even when resolver state is unavailable.

### 3. Add retry fields to pure contracts `AgentRunSchema`

- Added `AgentRunRetryPolicySchema` and `AgentRunRetryStateSchema` to `backend/packages/contracts/src/schemas.ts`.
- Added `retry_policy` and `retry_state` to `AgentRunSchema`.
- Exported `AgentRunRetryPolicy` and `AgentRunRetryState` types from `backend/packages/contracts/src/types.ts`.
- Added contract coverage proving retry fields validate under `AgentRunSchema`.

### 4. Historical doc wording cleanup

- Updated `docs/superpowers/plans/2026-06-24-agent-chat-workbench-p0.md` so:
  - `selected_skill_keys` is described as request input only,
  - active/loaded skills are described as derived from `skill.activated` events.

## Commands run and outcomes

- `rg -n "skill_id" backend frontend docs README.md`
  - no output, exit 1 as expected
- `cd backend && npm run typecheck`
  - passed
- `cd backend && npx vitest run tests/model/skill-load-tool.test.ts tests/capability/skill-policy.test.ts tests/contracts/schemas.test.ts`
  - passed
- `cd backend && npx vitest run tests/model/model-turn.test.ts tests/model/skill-context.test.ts`
  - passed
- `cd backend && npm run test`
  - passed (`36` files, `217` tests)
- `cd backend && npm run check:no-python-backend`
  - passed
- `cd backend && npm run examples:file-report`
  - passed

## Concerns

- Malformed historical `skill.activated` events now intentionally fail closed for skill-policy enforcement. That matches the requested safety direction, but older malformed events would need repair or replay if they exist in persisted data.
