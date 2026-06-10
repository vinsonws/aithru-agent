# @aithru/agent-server

Phase 3 server host for Aithru Agent Harness.

This is a dev server with in-memory-only state. Do not expose to public networks.

Currently uses ScriptedModelPort (scripted mock model) — not a real LLM.

## Dev server

```bash
pnpm --filter @aithru/agent-server dev
```

Default: http://127.0.0.1:4317

Configuration via environment variables:

- `AITHRU_AGENT_SERVER_HOST` — default `127.0.0.1`
- `AITHRU_AGENT_SERVER_PORT` — default `4317`

## API

### Health

```bash
curl -sS http://127.0.0.1:4317/health
```

### Create a run

```bash
curl -sS -X POST http://127.0.0.1:4317/runs \
  -H 'content-type: application/json' \
  -d '{"goal":"Analyze and write a report.","orgId":"org_1","actorUserId":"user_1","scopes":["*"]}'
```

### View run events

```bash
curl -sS http://127.0.0.1:4317/runs/<runId>/events
```

### View pending approvals

```bash
curl -sS 'http://127.0.0.1:4317/approvals?status=pending'
```

### Resolve an approval

```bash
curl -sS -X POST http://127.0.0.1:4317/approvals/<approvalId>/resolve \
  -H 'content-type: application/json' \
  -d '{"decision":"approved","comment":"ok"}'
```

### SSE event stream

```bash
curl -N http://127.0.0.1:4317/runs/<runId>/stream
```

## Run lifecycle

```
POST /runs                    → runId returned immediately
  → engine starts in background
  → emits run.created, run.started, …
  → ScriptedModelPort calls workspace.writeFile
  → approval.requested, run.paused
GET /approvals?status=pending → approvalId
POST /approvals/:id/resolve   → engine.resume()
  → run.resumed, tool.started, tool.completed, run.completed
```

## Verification commands

```bash
pnpm --filter @aithru/agent-server typecheck
pnpm --filter @aithru/agent-server build
pnpm --filter @aithru/agent-server test
```

## What this is NOT

- Not a Platform-hosted service (no auth, no tokens, no RBAC)
- Not integrated with Aithru Workbench
- Not using a real LLM
- Not using a database
- Not handling concurrent run limits or durability
