# Backend Package Workspace Structure Design

Date: 2026-06-29
Status: proposed

## Summary

Restructure the active TypeScript backend from a Python-like flat layer layout
into a private npm workspace with app and package boundaries.

The change is structural only. It must not change API behavior, event shape,
tool policy, persistence behavior, or the no-Python backend boundary.

## Goals

- Make `backend/` look and feel like a TypeScript package workspace.
- Preserve the existing Aithru Agent harness boundaries.
- Make dependency direction visible from package names and imports.
- Keep packages private and local; do not introduce publishing or versioning
  complexity.
- Move files and update imports without changing runtime behavior.

## Non-Goals

- Do not split the repository into multiple independently published npm
  packages.
- Do not introduce a new framework or build system.
- Do not change HTTP routes, SSE event contracts, schemas, or persistence
  semantics.
- Do not reintroduce Python backend code, Python workers, or Python runtime
  dependencies.
- Do not turn Agent runtime state into workflow definitions.

## Target Layout

```txt
backend/
  package.json
  tsconfig.json
  vitest.config.ts

  apps/
    api/
      src/
        app.ts
        cli.ts
        runtime.ts
        routes/
          approvals.ts
          health.ts
          runs.ts
          threads.ts

  packages/
    contracts/
      src/
        schemas.ts
        types.ts

    domain/
      src/
        errors.ts

    stream/
      src/
        events.ts
        index.ts
        redaction.ts
        sse.ts
        store.ts
        writer.ts

    trace/
      src/
        projector.ts
        spans.ts

    capabilities/
      src/
        audit.ts
        descriptors.ts
        policy.ts
        router.ts
        production-router.ts
        test-router.ts

    harness/
      src/
        harness.ts
        model-turn.ts
        retry.ts
        run-loop.ts

    model/
      src/
        profiles.ts
        provider-adapters.ts
        test-adapter.ts
        types.ts

    persistence/
      src/
        migrations.ts
        protocols.ts
        sqlite-store.ts
        store.ts

    external/
      src/
        controlled-web.ts
        mcp.ts
        workflow-capability.ts

    skills/
      src/
        loader.ts
        registry.ts

    memory/
      src/
        provider.ts

    snapshots/
      src/
        snapshot.ts
        summary.ts
        tree.ts

    subagents/
      src/
        runner.ts

    worker/
      src/
        external-run.ts
        recovery.ts
        runner.ts

  examples/
  scripts/
  tests/
```

Package names are private workspace names:

```txt
@aithru-agent/contracts
@aithru-agent/domain
@aithru-agent/stream
@aithru-agent/trace
@aithru-agent/capabilities
@aithru-agent/harness
@aithru-agent/model
@aithru-agent/persistence
@aithru-agent/external
@aithru-agent/skills
@aithru-agent/memory
@aithru-agent/snapshots
@aithru-agent/subagents
@aithru-agent/worker
@aithru-agent/api
```

## Dependency Direction

Allowed dependency flow:

```txt
apps/api
  -> worker, persistence, capabilities, model, skills, memory, stream,
     contracts

worker
  -> harness, persistence, stream, snapshots, capabilities

harness
  -> contracts, capabilities, model, stream

capabilities
  -> contracts, stream

model
  -> contracts

persistence
  -> contracts

stream
  -> contracts

trace
  -> contracts

snapshots
  -> contracts, trace
```

Rules:

- `contracts` has no runtime dependency on other backend packages.
- `model` never imports `capabilities`, `persistence`, `worker`, or `apps/api`.
- `capabilities` never imports `apps/api`.
- `apps/api` is the only HTTP/Fastify package.
- `apps/api/src/runtime.ts` is the composition root that wires concrete stores,
  routers, workers, providers, and model adapters.
- Package imports should use workspace package names instead of deep relative
  paths when crossing package boundaries.

## Import Style

Within a package, use relative imports:

```ts
import { redactPayload } from "./redaction.js";
```

Across packages, use package imports:

```ts
import type { AgentRun } from "@aithru-agent/contracts";
import { AgentEventWriter } from "@aithru-agent/stream";
```

Each package exposes a focused `src/index.ts` for cross-package imports. Deep
imports across package boundaries are avoided unless a package explicitly
exports a subpath later.

## Package Configuration

Root `backend/package.json` remains the command entrypoint and declares npm
workspaces:

```json
{
  "private": true,
  "workspaces": ["apps/*", "packages/*"]
}
```

Each workspace package has a minimal `package.json`:

```json
{
  "name": "@aithru-agent/stream",
  "private": true,
  "type": "module",
  "main": "src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  }
}
```

The first migration may keep a single root TypeScript and Vitest configuration
to avoid unnecessary build-system churn.

## Testing

Required verification after migration:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
npx tsx examples/approval_demo.ts
```

Tests may stay under `backend/tests/` in the first pass. Package-colocated tests
can be introduced later if package internals grow.

## Migration Plan

1. Add workspace package folders and package manifests.
2. Move source files from `src/*` into `apps/api/src` and `packages/*/src`.
3. Add package `index.ts` exports.
4. Rewrite imports from deep relative paths to workspace package names.
5. Update scripts, examples, docs, and no-Python checker paths if needed.
6. Run the full verification suite.

## Acceptance Criteria

- `backend/src/` no longer exists as the main source tree.
- Active source code lives under `backend/apps/*` and `backend/packages/*`.
- Cross-package imports use `@aithru-agent/*` workspace names.
- The backend still starts from `npm run dev`.
- The public HTTP API and SSE event contracts remain unchanged.
- The no-Python backend check still passes.
- All required verification commands pass.
