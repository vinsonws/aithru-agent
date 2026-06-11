# @aithru/agent-server

Phase 3 / Phase 4a server host for Aithru Agent Harness.

This is a dev server with in-memory-only state. Do not expose to public networks.

Currently uses ScriptedModelPort (scripted mock model) — not a real LLM.

## Modes

The agent-server supports two modes: **Standalone** (P3 dev server) and **Platform subsystem** (P4a).

### Standalone mode

No authentication, no platform integration.

```bash
pnpm --filter @aithru/agent-server dev
```

Default: http://127.0.0.1:4317

Configuration via environment variables:

- `AITHRU_AGENT_SERVER_HOST` — default `127.0.0.1`
- `AITHRU_AGENT_SERVER_PORT` — default `4317`

Routes:

```
GET  /health
GET  /me

POST /threads
GET  /threads
GET  /threads/:threadId
POST /threads/:threadId/messages
GET  /threads/:threadId/messages

POST /runs
GET  /runs
GET  /runs/:runId
GET  /runs/:runId/events
GET  /runs/:runId/stream
POST /runs/:runId/resume
POST /runs/:runId/cancel

GET  /approvals
GET  /approvals/:approvalId
POST /approvals/:approvalId/resolve
```

### Platform subsystem mode

Requires @aithru/subsystem-sdk-node and an Aithru Platform backend.

```bash
pnpm --filter @aithru/agent-server dev:platform
```

Routes are mounted under `/api/agent`:

```
GET  /health
GET  /api/agent/me

POST /api/agent/threads
GET  /api/agent/threads
GET  /api/agent/threads/:threadId
POST /api/agent/threads/:threadId/messages
GET  /api/agent/threads/:threadId/messages

POST /api/agent/runs
GET  /api/agent/runs
GET  /api/agent/runs/:runId
GET  /api/agent/runs/:runId/events
GET  /api/agent/runs/:runId/stream
POST /api/agent/runs/:runId/resume
POST /api/agent/runs/:runId/cancel

GET  /api/agent/approvals
GET  /api/agent/approvals/:approvalId
POST /api/agent/approvals/:approvalId/resolve
```

#### Required environment variables

Every production subsystem must be configurable through these five variables:

| Variable | Default | Used for |
|----------|---------|----------|
| `AITHRU_PLATFORM_URL` | `http://localhost:8080` | Platform backend — JWKS, authz, audit, manifest registration, token APIs |
| `AITHRU_APP_KEY` | `agent` | Subsystem app identity — permission namespace, token audience, manifest path |
| `AITHRU_CLIENT_SECRET` | `agent-secret` | Service client secret for Platform internal API auth |
| `AITHRU_PUBLIC_BASE_URL` | `http://localhost:PORT` | Browser-reachable subsystem URL — portal iframe loading |
| `AITHRU_INTERNAL_BASE_URL` | `http://localhost:PORT` | Platform/service-reachable subsystem URL — health checks, routing |

#### Convention-derived overrides

| Variable | Default | Used for |
|----------|---------|----------|
| `AITHRU_ISSUER` | `AITHRU_PLATFORM_URL` | JWT `iss` validation |
| `AITHRU_AUDIENCE` | `AITHRU_APP_KEY` | JWT `aud` validation |
| `AITHRU_CLIENT_ID` | `${AITHRU_APP_KEY}-client` | Service client id paired with `AITHRU_CLIENT_SECRET` |
| `AITHRU_SERVICE_NAME` | `${AITHRU_APP_KEY}-api` | Audit source, tracing, optional service policy matching |
| `AITHRU_HEALTH_URL` | `${AITHRU_INTERNAL_BASE_URL}/health` | Platform health checks |

#### Optional behavior controls

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` / `AITHRU_AGENT_SERVER_PORT` | `4317` | HTTP listen port |
| `AITHRU_SERVICE_VERSION` | `0.2.0-alpha.0` | Runtime/audit/debug metadata |
| `AITHRU_MANIFEST_LOCATION` | `apps/agent-server/aithru-app.yml` | Manifest file path |
| `AITHRU_REGISTRATION_ENABLED` | `true` | Auto-register manifest at startup |
| `AITHRU_FAIL_ON_REGISTRATION_ERROR` | `true` | Fail startup on manifest registration failure (set `false` for local dev) |

The config never accepts user, organization, session, or grant identity — runtime identity comes only from verified Platform-issued JWTs.

#### SDK dependency setup

`@aithru/subsystem-sdk-node` is published to an internal Nexus registry. To install:

Option A — Configure `.npmrc`:

```
@aithru:registry=http://192.168.1.11:8081/repository/xmap-npm/
```

Option B — Local npm link:

```bash
# In the SDK repo
cd subsystem-sdks/sdk-ts
npm run build
npm link

# In the agent repo
cd apps/agent-server
npm link @aithru/subsystem-sdk-node
```

#### Required platform setup

Before running platform mode, create in the Aithru Platform:

1. **App record**: `POST /api/admin/apps` — key = `agent`, name = `Aithru Agent`, integration mode = `iframe`
2. **Service client**: `POST /api/admin/apps/{appId}/service-clients` with scopes:
   - `manifest.register` — required for manifest registration
   - `audit.write` — required for audit event reporting
3. **User grants**: `POST /api/admin/app-user-context-grants` for test users:
   - `app_access` grant for portal entry
   - `agent.viewer` / `agent.operator` / `agent.admin` role grants as needed
4. **Service policy**: `POST /api/admin/service-policies` only if agent-server calls other subsystems

Do not create `app-grants` grants or resource registry entries — `POST /api/admin/app-grants` and
`/api/internal/apps/{appKey}/resources` are removed endpoints.

Agent business resources (threads, runs, workspaces, skills, artifacts) are owned by Agent, not
registered with Platform. Platform manages app identity, org context, tokens, scopes, grants,
connection policies, and audit.

The hosted frontend (`/` route) is a minimal iframe placeholder. A complete `agent-web` hosted app
will be built separately.

## API

### Create a run

```bash
curl -sS -X POST http://127.0.0.1:4317/runs \
  -H 'content-type: application/json' \
  -d '{"goal":"Analyze and write a report.","orgId":"org_1","actorUserId":"user_1","scopes":["*"]}'
```

In platform mode, `orgId`, `actorUserId`, and `scopes` come from the verified JWT — request body values are ignored for these fields.

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

In platform mode, SSE requires `agent.run.read` scope and token-based authentication.

### Current actor

```bash
curl -sS http://127.0.0.1:4317/me
```

```json
{
  "mode": "standalone",
  "actor": null
}
```

In platform mode:

```json
{
  "mode": "platform",
  "actor": {
    "actorType": "user",
    "userId": "user_123",
    "orgId": "org_123",
    "scopes": ["agent.run.create", "agent.run.read"],
    "roles": ["agent.operator"],
    "audience": "agent",
    "tokenType": "access"
  }
}
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

## Scope mapping (platform mode)

In platform mode, each API endpoint requires a specific scope:

| Endpoint | Scope |
|----------|-------|
| `GET /me` | `agent.app.view` |
| `POST /threads` | `agent.thread.write` |
| `GET /threads` | `agent.thread.read` |
| `GET /threads/:threadId` | `agent.thread.read` |
| `POST /threads/:threadId/messages` | `agent.thread.write` |
| `GET /threads/:threadId/messages` | `agent.thread.read` |
| `POST /runs` | `agent.run.create` |
| `GET /runs` | `agent.run.read` |
| `GET /runs/:runId` | `agent.run.read` |
| `GET /runs/:runId/events` | `agent.run.read` |
| `GET /runs/:runId/stream` | `agent.run.read` |
| `POST /runs/:runId/resume` | `agent.approval.resolve` |
| `POST /runs/:runId/cancel` | `agent.run.cancel` |
| `GET /approvals` | `agent.approval.read` |
| `GET /approvals/:approvalId` | `agent.approval.read` |
| `POST /approvals/:approvalId/resolve` | `agent.approval.resolve` |
| `GET /health` | *no auth* |

## Manifest

`apps/agent-server/aithru-app.yml` defines:

- **Permissions**: view, thread read/write, run create/read/cancel, approval read/resolve, workspace read/write, skill read/write, tool use
- **Roles**: viewer, operator, admin
- No platform resource types — Agent business resources are owned by Agent

## Platform mode behavior

- **CurrentActor**: extracted from JWT by SDK middleware, mapped to AgentHttpActor
- **Run identity**: orgId, actorUserId, scopes come from CurrentActor, never from request body
- **Audit**: run creation, run cancellation, and approval resolution produce audit events
- **Fail closed**: missing actor fields (orgId, userId) return 403; missing scopes return 403
- **No resource registration**: Agent threads, runs, workspaces, skills, and artifacts are Agent business resources — Platform is not a resource registry
- **Scope boundary**: requires `agent.*` scopes via `requireScope()` — app/org/group context helper not yet implemented; see [SDK README](../../../aithru-platform/subsystem-sdks/README.md) for future `requireAppPermission()` support

## Verification commands

```bash
pnpm --filter @aithru/agent-server typecheck
pnpm --filter @aithru/agent-server build
pnpm --filter @aithru/agent-server test
```

## What this is NOT (P3 / standalone)

- Not a Platform-hosted service (no auth, no tokens, no RBAC)
- Not integrated with Aithru Workbench
- Not using a real LLM
- Not using a database
- Not handling concurrent run limits or durability

## What this is NOT (P4a / platform mode)

- Not connected to Workbench workflow adapter
- Not connected to Core tool adapter
- Not using a real LLM (still ScriptedModelPort)
- No database persistence
- No complete Agent UI
- No subagents
- No sandbox execution
- No memory
- No delegated background tasks
- Agent todos/plans are not workflow graphs
