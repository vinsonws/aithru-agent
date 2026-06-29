# Backend Package Workspace Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `backend/` into a private npm workspace with `apps/api` and `packages/*` while preserving current behavior.

**Architecture:** Keep one backend runtime and one root command surface. Source moves from `backend/src/*` into private workspace packages; cross-package imports use `@aithru-agent/*`; `apps/api/src/runtime.ts` becomes the composition root that wires stores, routers, workers, providers, and model adapters.

**Tech Stack:** Node.js 22, TypeScript `NodeNext`, npm workspaces, Fastify, TypeBox, Vitest, tsx.

## Global Constraints

- Do not change HTTP routes, SSE event contracts, schemas, or persistence semantics.
- Do not introduce a new framework or build system.
- Do not reintroduce Python backend code, Python workers, or Python runtime dependencies.
- Do not turn Agent runtime state into workflow definitions.
- Keep packages private and local; do not introduce independent package publishing.
- Keep `npm run typecheck`, `npm run test`, `npm run check:no-python-backend`, `npm run examples:file-report`, and `npx tsx examples/approval_demo.ts` working from `backend/`.
- Preserve the current `backend/` directory name. If the workspace still has uncommitted `backend-ts -> backend` rename changes, continue from `backend/` and do not recreate `backend-ts/`.

---

## File Structure

Create:

- `backend/apps/api/package.json`: private workspace package manifest for the API app.
- `backend/apps/api/src/index.ts`: API package exports.
- `backend/apps/api/src/app.ts`: moved from `backend/src/api/app.ts`.
- `backend/apps/api/src/cli.ts`: moved from `backend/src/cli/server.ts`.
- `backend/apps/api/src/runtime.ts`: moved from `backend/src/application/runtime.ts`.
- `backend/apps/api/src/routes/*.ts`: moved from `backend/src/api/{approvals,health,runs,threads}.ts`.
- `backend/packages/*/package.json`: private package manifests.
- `backend/packages/*/src/index.ts`: focused exports for each package.

Move:

- `backend/src/contracts/*` -> `backend/packages/contracts/src/*`
- `backend/src/stream/*` -> `backend/packages/stream/src/*`
- `backend/src/trace/*` -> `backend/packages/trace/src/*`
- `backend/src/capabilities/*` -> `backend/packages/capabilities/src/*`
- `backend/src/core/*` -> `backend/packages/harness/src/*`
- `backend/src/model/*` -> `backend/packages/model/src/*`
- `backend/src/persistence/*` -> `backend/packages/persistence/src/*`
- `backend/src/external/*` -> `backend/packages/external/src/*`
- `backend/src/skills/*` -> `backend/packages/skills/src/*`
- `backend/src/memory/*` -> `backend/packages/memory/src/*`
- `backend/src/snapshots/*` -> `backend/packages/snapshots/src/*`
- `backend/src/subagent/*` -> `backend/packages/subagents/src/*`
- `backend/src/worker/*` -> `backend/packages/worker/src/*`

Modify:

- `backend/package.json`: add npm workspaces and update scripts to `apps/api/src/cli.ts`.
- `backend/package-lock.json`: refresh with `npm install`.
- `backend/tsconfig.json`: include `apps/**/*.ts`, `packages/**/*.ts`, `tests/**/*.ts`, and `examples/**/*.ts`; add package path aliases.
- `backend/vitest.config.ts`: add Vite/Vitest aliases for `@aithru-agent/*`.
- `backend/examples/*.ts`: import from workspace packages.
- `backend/tests/**/*.test.ts`: import from workspace packages.
- `backend/scripts/check-no-python.mjs`: scan `apps`, `packages`, `examples`, `scripts`, and `package.json`.
- Docs that reference `backend/src/*`: update to `backend/apps/api/src/*` or `backend/packages/*/src/*`.

---

### Task 1: Workspace Scaffolding and Resolver Configuration

**Files:**

- Modify: `backend/package.json`
- Modify: `backend/tsconfig.json`
- Modify: `backend/vitest.config.ts`
- Create: `backend/apps/api/package.json`
- Create: `backend/packages/contracts/package.json`
- Create: `backend/packages/domain/package.json`
- Create: `backend/packages/stream/package.json`
- Create: `backend/packages/trace/package.json`
- Create: `backend/packages/capabilities/package.json`
- Create: `backend/packages/harness/package.json`
- Create: `backend/packages/model/package.json`
- Create: `backend/packages/persistence/package.json`
- Create: `backend/packages/external/package.json`
- Create: `backend/packages/skills/package.json`
- Create: `backend/packages/memory/package.json`
- Create: `backend/packages/snapshots/package.json`
- Create: `backend/packages/subagents/package.json`
- Create: `backend/packages/worker/package.json`

**Interfaces:**

- Consumes: current root `backend/package.json`, `backend/tsconfig.json`, and `backend/vitest.config.ts`.
- Produces: npm workspace manifests and TypeScript/Vitest alias resolution for `@aithru-agent/*`.

- [ ] **Step 1: Update root package manifest**

Replace `backend/package.json` with:

```json
{
  "name": "aithru-agent-backend",
  "version": "0.1.0",
  "description": "TypeScript backend for the Aithru Agent harness.",
  "private": true,
  "type": "module",
  "workspaces": [
    "apps/*",
    "packages/*"
  ],
  "scripts": {
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:contracts": "vitest run tests/contracts/",
    "test:stream-golden": "vitest run tests/stream/",
    "test:capability-boundary": "vitest run tests/capability/",
    "check:no-python-backend": "node scripts/check-no-python.mjs",
    "examples:file-report": "npx tsx examples/file_report_agent.ts",
    "dev": "npx tsx apps/api/src/cli.ts",
    "start": "node --loader ts-node/esm apps/api/src/cli.ts"
  },
  "dependencies": {
    "@fastify/swagger": "^9.4.0",
    "@sinclair/typebox": "^0.34.0",
    "fastify": "^5.2.0",
    "nanoid": "^5.1.0",
    "sql.js": "^1.14.1"
  },
  "devDependencies": {
    "@types/node": "^22.10.0",
    "@types/sql.js": "^1.4.11",
    "tsx": "^4.19.0",
    "typescript": "^5.7.0",
    "vitest": "^3.0.0"
  },
  "engines": {
    "node": ">=22.0.0"
  }
}
```

- [ ] **Step 2: Update TypeScript configuration**

Replace `backend/tsconfig.json` with:

```json
{
  "compilerOptions": {
    "target": "ES2023",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2023"],
    "outDir": "dist",
    "rootDir": ".",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "baseUrl": ".",
    "paths": {
      "@aithru-agent/api": ["apps/api/src/index.ts"],
      "@aithru-agent/contracts": ["packages/contracts/src/index.ts"],
      "@aithru-agent/domain": ["packages/domain/src/index.ts"],
      "@aithru-agent/stream": ["packages/stream/src/index.ts"],
      "@aithru-agent/trace": ["packages/trace/src/index.ts"],
      "@aithru-agent/capabilities": ["packages/capabilities/src/index.ts"],
      "@aithru-agent/harness": ["packages/harness/src/index.ts"],
      "@aithru-agent/model": ["packages/model/src/index.ts"],
      "@aithru-agent/persistence": ["packages/persistence/src/index.ts"],
      "@aithru-agent/external": ["packages/external/src/index.ts"],
      "@aithru-agent/skills": ["packages/skills/src/index.ts"],
      "@aithru-agent/memory": ["packages/memory/src/index.ts"],
      "@aithru-agent/snapshots": ["packages/snapshots/src/index.ts"],
      "@aithru-agent/subagents": ["packages/subagents/src/index.ts"],
      "@aithru-agent/worker": ["packages/worker/src/index.ts"]
    }
  },
  "include": [
    "apps/**/*.ts",
    "packages/**/*.ts",
    "examples/**/*.ts",
    "tests/**/*.ts",
    "scripts/**/*.mjs"
  ],
  "exclude": ["node_modules", "dist"]
}
```

- [ ] **Step 3: Update Vitest configuration**

Replace `backend/vitest.config.ts` with:

```ts
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@aithru-agent/api": resolve(root, "apps/api/src/index.ts"),
      "@aithru-agent/contracts": resolve(root, "packages/contracts/src/index.ts"),
      "@aithru-agent/domain": resolve(root, "packages/domain/src/index.ts"),
      "@aithru-agent/stream": resolve(root, "packages/stream/src/index.ts"),
      "@aithru-agent/trace": resolve(root, "packages/trace/src/index.ts"),
      "@aithru-agent/capabilities": resolve(root, "packages/capabilities/src/index.ts"),
      "@aithru-agent/harness": resolve(root, "packages/harness/src/index.ts"),
      "@aithru-agent/model": resolve(root, "packages/model/src/index.ts"),
      "@aithru-agent/persistence": resolve(root, "packages/persistence/src/index.ts"),
      "@aithru-agent/external": resolve(root, "packages/external/src/index.ts"),
      "@aithru-agent/skills": resolve(root, "packages/skills/src/index.ts"),
      "@aithru-agent/memory": resolve(root, "packages/memory/src/index.ts"),
      "@aithru-agent/snapshots": resolve(root, "packages/snapshots/src/index.ts"),
      "@aithru-agent/subagents": resolve(root, "packages/subagents/src/index.ts"),
      "@aithru-agent/worker": resolve(root, "packages/worker/src/index.ts")
    }
  },
  test: {
    globals: true,
    include: ["tests/**/*.test.ts"]
  }
});
```

- [ ] **Step 4: Create workspace package manifests**

Create each package manifest with this exact pattern, changing only `name`.

Example `backend/packages/contracts/package.json`:

```json
{
  "name": "@aithru-agent/contracts",
  "private": true,
  "type": "module",
  "main": "src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  }
}
```

Create the same manifest for:

```txt
backend/apps/api/package.json                 name @aithru-agent/api
backend/packages/domain/package.json          name @aithru-agent/domain
backend/packages/stream/package.json          name @aithru-agent/stream
backend/packages/trace/package.json           name @aithru-agent/trace
backend/packages/capabilities/package.json    name @aithru-agent/capabilities
backend/packages/harness/package.json         name @aithru-agent/harness
backend/packages/model/package.json           name @aithru-agent/model
backend/packages/persistence/package.json     name @aithru-agent/persistence
backend/packages/external/package.json        name @aithru-agent/external
backend/packages/skills/package.json          name @aithru-agent/skills
backend/packages/memory/package.json          name @aithru-agent/memory
backend/packages/snapshots/package.json       name @aithru-agent/snapshots
backend/packages/subagents/package.json       name @aithru-agent/subagents
backend/packages/worker/package.json          name @aithru-agent/worker
```

- [ ] **Step 5: Refresh lockfile**

Run:

```bash
cd backend
npm install
```

Expected: `package-lock.json` updates with workspace package entries and exits 0.

- [ ] **Step 6: Verify the scaffold still compiles before moving code**

Run:

```bash
cd backend
npm run typecheck
```

Expected: PASS. At this point no imports have changed yet, so this proves the workspace config did not break the current source tree.

- [ ] **Step 7: Commit**

```bash
git add backend/package.json backend/package-lock.json backend/tsconfig.json backend/vitest.config.ts backend/apps backend/packages
git commit -m "chore(backend): add workspace package scaffold"
```

---

### Task 2: Move Foundation Packages

**Files:**

- Move: `backend/src/contracts/*` -> `backend/packages/contracts/src/*`
- Move: `backend/src/stream/*` -> `backend/packages/stream/src/*`
- Move: `backend/src/trace/*` -> `backend/packages/trace/src/*`
- Create/Modify: `backend/packages/contracts/src/index.ts`
- Create/Modify: `backend/packages/stream/src/index.ts`
- Create/Modify: `backend/packages/trace/src/index.ts`
- Modify: `backend/tests/contracts/schemas.test.ts`
- Modify: `backend/tests/stream/*.test.ts`
- Modify: `backend/tests/trace/projector.test.ts`

**Interfaces:**

- Consumes: package aliases from Task 1.
- Produces: `@aithru-agent/contracts`, `@aithru-agent/stream`, and `@aithru-agent/trace`.

- [ ] **Step 1: Move contract files**

```powershell
New-Item -ItemType Directory -Force backend/packages/contracts/src | Out-Null
git mv backend/src/contracts/schemas.ts backend/packages/contracts/src/schemas.ts
git mv backend/src/contracts/types.ts backend/packages/contracts/src/types.ts
git mv backend/src/contracts/index.ts backend/packages/contracts/src/index.ts
```

- [ ] **Step 2: Set contract exports**

Replace `backend/packages/contracts/src/index.ts` with:

```ts
export * from "./schemas.js";
export * from "./types.js";
```

- [ ] **Step 3: Move stream files**

```powershell
New-Item -ItemType Directory -Force backend/packages/stream/src | Out-Null
git mv backend/src/stream/events.ts backend/packages/stream/src/events.ts
git mv backend/src/stream/index.ts backend/packages/stream/src/index.ts
git mv backend/src/stream/redaction.ts backend/packages/stream/src/redaction.ts
git mv backend/src/stream/sse.ts backend/packages/stream/src/sse.ts
git mv backend/src/stream/store.ts backend/packages/stream/src/store.ts
git mv backend/src/stream/writer.ts backend/packages/stream/src/writer.ts
```

- [ ] **Step 4: Update stream imports and exports**

In `backend/packages/stream/src/events.ts`, replace:

```ts
} from "../contracts/types.js";
```

with:

```ts
} from "@aithru-agent/contracts";
```

In `backend/packages/stream/src/sse.ts`, replace:

```ts
import type { AgentStreamEvent } from "../contracts/types.js";
```

with:

```ts
import type { AgentStreamEvent } from "@aithru-agent/contracts";
```

In `backend/packages/stream/src/store.ts`, replace:

```ts
import type { AgentStreamEvent } from "../contracts/types.js";
```

with:

```ts
import type { AgentStreamEvent } from "@aithru-agent/contracts";
```

In `backend/packages/stream/src/writer.ts`, replace:

```ts
import type { AgentStreamEvent, AgentStreamSource } from "../contracts/types.js";
```

with:

```ts
import type { AgentStreamEvent, AgentStreamSource } from "@aithru-agent/contracts";
```

Keep same-package imports such as `./events.js` and `./redaction.js` relative.

Replace `backend/packages/stream/src/index.ts` with:

```ts
export * from "./events.js";
export { InMemoryAgentEventStore } from "./store.js";
export { formatSseEvent, formatSseComment } from "./sse.js";
export { redactPayload, REDACTED_VALUE } from "./redaction.js";
export { AgentEventWriter } from "./writer.js";
```

- [ ] **Step 5: Move trace files**

```powershell
New-Item -ItemType Directory -Force backend/packages/trace/src | Out-Null
git mv backend/src/trace/index.ts backend/packages/trace/src/index.ts
git mv backend/src/trace/projector.ts backend/packages/trace/src/projector.ts
git mv backend/src/trace/spans.ts backend/packages/trace/src/spans.ts
```

- [ ] **Step 6: Update trace imports and exports**

In `backend/packages/trace/src/projector.ts`, replace:

```ts
import type { AgentStreamEvent } from "../contracts/types.js";
```

with:

```ts
import type { AgentStreamEvent } from "@aithru-agent/contracts";
```

Replace `backend/packages/trace/src/index.ts` with:

```ts
export * from "./spans.js";
export * from "./projector.js";
```

- [ ] **Step 7: Update foundation tests**

Apply these import replacements:

```txt
backend/tests/contracts/schemas.test.ts:
  ../../src/contracts/schemas.js -> @aithru-agent/contracts

backend/tests/stream/events.test.ts:
  ../../src/stream/events.js -> @aithru-agent/stream

backend/tests/stream/redaction.test.ts:
  ../../src/stream/redaction.js -> @aithru-agent/stream

backend/tests/stream/sse.test.ts:
  ../../src/stream/sse.js -> @aithru-agent/stream
  ../../src/contracts/types.js -> @aithru-agent/contracts

backend/tests/trace/projector.test.ts:
  ../../src/trace/projector.js -> @aithru-agent/trace
  ../../src/contracts/types.js -> @aithru-agent/contracts
```

Example final import block for `backend/tests/stream/sse.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatSseEvent, formatSseComment } from "@aithru-agent/stream";
import type { AgentStreamEvent } from "@aithru-agent/contracts";
```

- [ ] **Step 8: Verify foundation packages**

Run:

```bash
cd backend
npm run typecheck
npm run test:contracts
npm run test:stream-golden
vitest run tests/trace/projector.test.ts
```

Expected: all commands pass.

- [ ] **Step 9: Commit**

```bash
git add backend/packages/contracts backend/packages/stream backend/packages/trace backend/tests/contracts backend/tests/stream backend/tests/trace backend/src
git commit -m "refactor(backend): move contracts stream and trace packages"
```

---

### Task 3: Move Infrastructure and Capability Packages

**Files:**

- Move: `backend/src/persistence/*` -> `backend/packages/persistence/src/*`
- Move: `backend/src/capabilities/*` -> `backend/packages/capabilities/src/*`
- Move: `backend/src/external/*` -> `backend/packages/external/src/*`
- Move: `backend/src/model/*` -> `backend/packages/model/src/*`
- Move: `backend/src/skills/*` -> `backend/packages/skills/src/*`
- Move: `backend/src/memory/*` -> `backend/packages/memory/src/*`
- Modify: related package `index.ts` exports.
- Modify: tests under `backend/tests/{capability,external,model,persistence,skills,memory}`.

**Interfaces:**

- Consumes: `@aithru-agent/contracts`, `@aithru-agent/stream`.
- Produces: `@aithru-agent/persistence`, `@aithru-agent/capabilities`, `@aithru-agent/external`, `@aithru-agent/model`, `@aithru-agent/skills`, `@aithru-agent/memory`.

- [ ] **Step 1: Move persistence package**

```powershell
New-Item -ItemType Directory -Force backend/packages/persistence/src | Out-Null
git mv backend/src/persistence/index.ts backend/packages/persistence/src/index.ts
git mv backend/src/persistence/migrations.ts backend/packages/persistence/src/migrations.ts
git mv backend/src/persistence/protocols.ts backend/packages/persistence/src/protocols.ts
git mv backend/src/persistence/sqlite-store.ts backend/packages/persistence/src/sqlite-store.ts
git mv backend/src/persistence/store.ts backend/packages/persistence/src/store.ts
```

Replace cross-package imports:

```txt
../contracts/types.js -> @aithru-agent/contracts
../contracts/schemas.js -> @aithru-agent/contracts
```

Replace `backend/packages/persistence/src/index.ts` with:

```ts
export * from "./protocols.js";
export * from "./store.js";
export * from "./sqlite-store.js";
export * from "./migrations.js";
```

- [ ] **Step 2: Move capabilities package**

```powershell
New-Item -ItemType Directory -Force backend/packages/capabilities/src | Out-Null
git mv backend/src/capabilities/audit.ts backend/packages/capabilities/src/audit.ts
git mv backend/src/capabilities/descriptors.ts backend/packages/capabilities/src/descriptors.ts
git mv backend/src/capabilities/index.ts backend/packages/capabilities/src/index.ts
git mv backend/src/capabilities/policy.ts backend/packages/capabilities/src/policy.ts
git mv backend/src/capabilities/production-router.ts backend/packages/capabilities/src/production-router.ts
git mv backend/src/capabilities/router.ts backend/packages/capabilities/src/router.ts
git mv backend/src/capabilities/test-router.ts backend/packages/capabilities/src/test-router.ts
```

Replace cross-package imports:

```txt
../contracts/types.js -> @aithru-agent/contracts
../stream/writer.js -> @aithru-agent/stream
../stream/events.js -> @aithru-agent/stream
../persistence/protocols.js -> @aithru-agent/persistence
```

Replace `backend/packages/capabilities/src/index.ts` with:

```ts
export * from "./descriptors.js";
export * from "./policy.js";
export * from "./router.js";
export * from "./production-router.js";
export * from "./test-router.js";
export * from "./audit.js";
```

- [ ] **Step 3: Move external package**

```powershell
New-Item -ItemType Directory -Force backend/packages/external/src | Out-Null
git mv backend/src/external/controlled-web.ts backend/packages/external/src/controlled-web.ts
git mv backend/src/external/index.ts backend/packages/external/src/index.ts
git mv backend/src/external/mcp.ts backend/packages/external/src/mcp.ts
git mv backend/src/external/workflow-capability.ts backend/packages/external/src/workflow-capability.ts
```

Replace cross-package imports:

```txt
../capabilities/descriptors.js -> @aithru-agent/capabilities
../capabilities/router.js -> @aithru-agent/capabilities
../contracts/types.js -> @aithru-agent/contracts
```

Replace `backend/packages/external/src/index.ts` with:

```ts
export * from "./controlled-web.js";
export * from "./mcp.js";
export * from "./workflow-capability.js";
```

- [ ] **Step 4: Move model package**

```powershell
New-Item -ItemType Directory -Force backend/packages/model/src | Out-Null
git mv backend/src/model/index.ts backend/packages/model/src/index.ts
git mv backend/src/model/profiles.ts backend/packages/model/src/profiles.ts
git mv backend/src/model/provider-adapters.ts backend/packages/model/src/provider-adapters.ts
git mv backend/src/model/test-adapter.ts backend/packages/model/src/test-adapter.ts
git mv backend/src/model/types.ts backend/packages/model/src/types.ts
```

Replace cross-package imports:

```txt
../contracts/types.js -> @aithru-agent/contracts
../capabilities/descriptors.js -> @aithru-agent/capabilities
```

Replace `backend/packages/model/src/index.ts` with:

```ts
export * from "./types.js";
export * from "./profiles.js";
export * from "./provider-adapters.js";
export * from "./test-adapter.js";
```

- [ ] **Step 5: Move skills and memory packages**

```powershell
New-Item -ItemType Directory -Force backend/packages/skills/src | Out-Null
git mv backend/src/skills/index.ts backend/packages/skills/src/index.ts
git mv backend/src/skills/loader.ts backend/packages/skills/src/loader.ts
git mv backend/src/skills/registry.ts backend/packages/skills/src/registry.ts

New-Item -ItemType Directory -Force backend/packages/memory/src | Out-Null
git mv backend/src/memory/index.ts backend/packages/memory/src/index.ts
git mv backend/src/memory/provider.ts backend/packages/memory/src/provider.ts
```

Replace `backend/packages/skills/src/index.ts` with:

```ts
export * from "./loader.js";
export * from "./registry.js";
```

Replace `backend/packages/memory/src/index.ts` with:

```ts
export * from "./provider.js";
```

- [ ] **Step 6: Update infrastructure tests**

Apply these import replacements:

```txt
../../src/persistence/store.js -> @aithru-agent/persistence
../../src/persistence/sqlite-store.js -> @aithru-agent/persistence
../../src/persistence/protocols.js -> @aithru-agent/persistence
../../src/capabilities/production-router.js -> @aithru-agent/capabilities
../../src/capabilities/router.js -> @aithru-agent/capabilities
../../src/capabilities/policy.js -> @aithru-agent/capabilities
../../src/capabilities/descriptors.js -> @aithru-agent/capabilities
../../src/external/controlled-web.js -> @aithru-agent/external
../../src/external/mcp.js -> @aithru-agent/external
../../src/external/workflow-capability.js -> @aithru-agent/external
../../src/model/profiles.js -> @aithru-agent/model
../../src/model/provider-adapters.js -> @aithru-agent/model
../../src/model/test-adapter.js -> @aithru-agent/model
../../src/model/types.js -> @aithru-agent/model
../../src/skills/loader.js -> @aithru-agent/skills
../../src/skills/registry.js -> @aithru-agent/skills
../../src/memory/provider.js -> @aithru-agent/memory
../../src/stream/writer.js -> @aithru-agent/stream
../../src/contracts/types.js -> @aithru-agent/contracts
```

- [ ] **Step 7: Verify infrastructure packages**

Run:

```bash
cd backend
npm run typecheck
vitest run tests/capability tests/external tests/model tests/persistence tests/skills tests/memory
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/packages backend/tests backend/src
git commit -m "refactor(backend): move infrastructure packages"
```

---

### Task 4: Move Harness, Worker, Snapshots, and Subagents

**Files:**

- Move: `backend/src/core/*` -> `backend/packages/harness/src/*`
- Move: `backend/src/worker/*` -> `backend/packages/worker/src/*`
- Move: `backend/src/snapshots/*` -> `backend/packages/snapshots/src/*`
- Move: `backend/src/subagent/*` -> `backend/packages/subagents/src/*`
- Modify: related package `index.ts` exports.
- Modify: tests under `backend/tests/{core,worker,snapshots,subagent,integration}` where they import moved modules.

**Interfaces:**

- Consumes: `@aithru-agent/contracts`, `@aithru-agent/capabilities`, `@aithru-agent/model`, `@aithru-agent/persistence`, `@aithru-agent/stream`, `@aithru-agent/trace`.
- Produces: `@aithru-agent/harness`, `@aithru-agent/worker`, `@aithru-agent/snapshots`, `@aithru-agent/subagents`.

- [ ] **Step 1: Move harness package**

```powershell
New-Item -ItemType Directory -Force backend/packages/harness/src | Out-Null
git mv backend/src/core/errors.ts backend/packages/harness/src/errors.ts
git mv backend/src/core/harness.ts backend/packages/harness/src/harness.ts
git mv backend/src/core/index.ts backend/packages/harness/src/index.ts
git mv backend/src/core/model-turn.ts backend/packages/harness/src/model-turn.ts
git mv backend/src/core/retry.ts backend/packages/harness/src/retry.ts
git mv backend/src/core/run-loop.ts backend/packages/harness/src/run-loop.ts
```

Replace cross-package imports:

```txt
../contracts/types.js -> @aithru-agent/contracts
../contracts/schemas.js -> @aithru-agent/contracts
../persistence/protocols.js -> @aithru-agent/persistence
../stream/writer.js -> @aithru-agent/stream
../stream/events.js -> @aithru-agent/stream
../capabilities/router.js -> @aithru-agent/capabilities
../capabilities/descriptors.js -> @aithru-agent/capabilities
../model/types.js -> @aithru-agent/model
```

Replace `backend/packages/harness/src/index.ts` with:

```ts
export * from "./errors.js";
export * from "./harness.js";
export * from "./model-turn.js";
export * from "./retry.js";
export * from "./run-loop.js";
```

- [ ] **Step 2: Move worker package**

```powershell
New-Item -ItemType Directory -Force backend/packages/worker/src | Out-Null
git mv backend/src/worker/external-run.ts backend/packages/worker/src/external-run.ts
git mv backend/src/worker/index.ts backend/packages/worker/src/index.ts
git mv backend/src/worker/recovery.ts backend/packages/worker/src/recovery.ts
git mv backend/src/worker/runner.ts backend/packages/worker/src/runner.ts
```

Replace cross-package imports:

```txt
../contracts/types.js -> @aithru-agent/contracts
../contracts/schemas.js -> @aithru-agent/contracts
../persistence/protocols.js -> @aithru-agent/persistence
../stream/writer.js -> @aithru-agent/stream
../stream/events.js -> @aithru-agent/stream
../capabilities/router.js -> @aithru-agent/capabilities
../core/harness.js -> @aithru-agent/harness
```

Replace `backend/packages/worker/src/index.ts` with:

```ts
export * from "./external-run.js";
export * from "./recovery.js";
export * from "./runner.js";
```

- [ ] **Step 3: Move snapshots and subagents**

```powershell
New-Item -ItemType Directory -Force backend/packages/snapshots/src | Out-Null
git mv backend/src/snapshots/index.ts backend/packages/snapshots/src/index.ts
git mv backend/src/snapshots/snapshot.ts backend/packages/snapshots/src/snapshot.ts
git mv backend/src/snapshots/summary.ts backend/packages/snapshots/src/summary.ts
git mv backend/src/snapshots/tree.ts backend/packages/snapshots/src/tree.ts

New-Item -ItemType Directory -Force backend/packages/subagents/src | Out-Null
git mv backend/src/subagent/index.ts backend/packages/subagents/src/index.ts
git mv backend/src/subagent/runner.ts backend/packages/subagents/src/runner.ts
```

Replace cross-package imports:

```txt
../contracts/types.js -> @aithru-agent/contracts
../trace/projector.js -> @aithru-agent/trace
../persistence/protocols.js -> @aithru-agent/persistence
```

Replace `backend/packages/snapshots/src/index.ts` with:

```ts
export * from "./snapshot.js";
export * from "./summary.js";
export * from "./tree.js";
```

Replace `backend/packages/subagents/src/index.ts` with:

```ts
export * from "./runner.js";
```

- [ ] **Step 4: Update harness and worker tests**

Apply these import replacements:

```txt
../../src/core/errors.js -> @aithru-agent/harness
../../src/core/harness.js -> @aithru-agent/harness
../../src/core/model-turn.js -> @aithru-agent/harness
../../src/core/retry.js -> @aithru-agent/harness
../../src/core/run-loop.js -> @aithru-agent/harness
../../src/worker/external-run.js -> @aithru-agent/worker
../../src/worker/recovery.js -> @aithru-agent/worker
../../src/worker/runner.js -> @aithru-agent/worker
../../src/snapshots/snapshot.js -> @aithru-agent/snapshots
../../src/snapshots/summary.js -> @aithru-agent/snapshots
../../src/snapshots/tree.js -> @aithru-agent/snapshots
../../src/subagent/runner.js -> @aithru-agent/subagents
```

- [ ] **Step 5: Verify harness and worker packages**

Run:

```bash
cd backend
npm run typecheck
vitest run tests/core tests/worker tests/snapshots tests/subagent tests/integration/approval-flow.test.ts
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/packages backend/tests backend/src
git commit -m "refactor(backend): move harness worker and projection packages"
```

---

### Task 5: Move API App and Runtime Composition Root

**Files:**

- Move: `backend/src/api/app.ts` -> `backend/apps/api/src/app.ts`
- Move: `backend/src/api/{approvals,health,runs,threads}.ts` -> `backend/apps/api/src/routes/*.ts`
- Move: `backend/src/api/index.ts` -> `backend/apps/api/src/index.ts`
- Move: `backend/src/cli/server.ts` -> `backend/apps/api/src/cli.ts`
- Move: `backend/src/application/runtime.ts` -> `backend/apps/api/src/runtime.ts`
- Remove: empty `backend/src/application/index.ts`
- Remove: empty `backend/src/cli/index.ts`
- Modify: `backend/tests/integration/api.test.ts`

**Interfaces:**

- Consumes: all packages from Tasks 2-4.
- Produces: `@aithru-agent/api` with `createApp`, `createRuntime`, and `getRuntime`.

- [ ] **Step 1: Move API and runtime files**

```powershell
New-Item -ItemType Directory -Force backend/apps/api/src/routes | Out-Null
git mv backend/src/api/app.ts backend/apps/api/src/app.ts
git mv backend/src/api/approvals.ts backend/apps/api/src/routes/approvals.ts
git mv backend/src/api/health.ts backend/apps/api/src/routes/health.ts
git mv backend/src/api/runs.ts backend/apps/api/src/routes/runs.ts
git mv backend/src/api/threads.ts backend/apps/api/src/routes/threads.ts
git mv backend/src/api/index.ts backend/apps/api/src/index.ts
git mv backend/src/cli/server.ts backend/apps/api/src/cli.ts
git mv backend/src/application/runtime.ts backend/apps/api/src/runtime.ts
git rm backend/src/application/index.ts
git rm backend/src/cli/index.ts
```

- [ ] **Step 2: Update API app imports**

Replace `backend/apps/api/src/app.ts` with:

```ts
import Fastify from "fastify";
import { createRuntime } from "./runtime.js";
import { registerApprovalRoutes } from "./routes/approvals.js";
import { registerHealthRoutes } from "./routes/health.js";
import { registerRunRoutes } from "./routes/runs.js";
import { registerThreadRoutes } from "./routes/threads.js";

export async function createApp() {
  const app = Fastify({ logger: true });

  await createRuntime();

  registerHealthRoutes(app);
  registerThreadRoutes(app);
  registerRunRoutes(app);
  registerApprovalRoutes(app);

  return app;
}
```

- [ ] **Step 3: Update runtime composition imports**

Replace the import block in `backend/apps/api/src/runtime.ts` with:

```ts
import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import { ScriptedHarnessCore } from "@aithru-agent/harness";
import { AgentEventWriter } from "@aithru-agent/stream";
import { InMemoryStore, SqliteStore, type AgentStore } from "@aithru-agent/persistence";
import { WorkerRunner } from "@aithru-agent/worker";
```

Keep the existing `AgentRuntime`, `createRuntime`, and `getRuntime` bodies unchanged.

- [ ] **Step 4: Update route imports**

Apply these replacements in `backend/apps/api/src/routes/*.ts`:

```txt
../application/runtime.js -> ../runtime.js
../contracts/types.js -> @aithru-agent/contracts
../contracts/schemas.js -> @aithru-agent/contracts
../stream/sse.js -> @aithru-agent/stream
../stream/events.js -> @aithru-agent/stream
../trace/projector.js -> @aithru-agent/trace
../snapshots/snapshot.js -> @aithru-agent/snapshots
../capabilities/audit.js -> @aithru-agent/capabilities
```

- [ ] **Step 5: Update API exports and CLI**

Replace `backend/apps/api/src/index.ts` with:

```ts
export { createApp } from "./app.js";
export { createRuntime, getRuntime, type AgentRuntime } from "./runtime.js";
```

In `backend/apps/api/src/cli.ts`, ensure the first line is:

```ts
import { createApp } from "./app.js";
```

- [ ] **Step 6: Update API tests**

In `backend/tests/integration/api.test.ts`, replace:

```ts
import { createApp } from "../../src/api/app.js";
```

with:

```ts
import { createApp } from "@aithru-agent/api";
```

- [ ] **Step 7: Verify API app**

Run:

```bash
cd backend
npm run typecheck
vitest run tests/integration/api.test.ts tests/integration/capability-audit.test.ts
```

Expected: selected integration tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/apps backend/packages backend/tests backend/src backend/package.json backend/tsconfig.json backend/vitest.config.ts
git commit -m "refactor(backend): move api app into workspace"
```

---

### Task 6: Update Examples, Scripts, Docs, and Remove Legacy Source Tree

**Files:**

- Modify: `backend/examples/file_report_agent.ts`
- Modify: `backend/examples/approval_demo.ts`
- Modify: `backend/scripts/check-no-python.mjs`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/00-agent-harness-design.md`
- Modify: `docs/02-complete-harness-architecture.md`
- Modify: `docs/03-stream-protocol.md`
- Modify: `docs/05-capability-router.md`
- Modify: `docs/06-harness-engine-adapter-strategy.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/superpowers/README.md`
- Modify: `docs/superpowers/specs/2026-06-25-skill-package-registry-design.md`
- Modify: `docs/superpowers/specs/2026-06-29-native-ts-agent-backend-replacement-design.md`
- Modify: `docs/superpowers/specs/2026-06-29-tool-result-recovery-loop-design.md`
- Delete: empty `backend/src/` directory if it remains.

**Interfaces:**

- Consumes: workspace package imports and app path from Tasks 1-5.
- Produces: no `backend/src` references in active docs, scripts, examples, or tests.

- [ ] **Step 1: Update example imports**

Apply these replacements:

```txt
backend/examples/file_report_agent.ts:
  ../src/application/runtime.js -> @aithru-agent/api
  ../src/contracts/types.js -> @aithru-agent/contracts
  ../src/stream/events.js -> @aithru-agent/stream

backend/examples/approval_demo.ts:
  ../src/application/runtime.js -> @aithru-agent/api
  ../src/contracts/types.js -> @aithru-agent/contracts
  ../src/stream/events.js -> @aithru-agent/stream
  ../src/trace/projector.js -> @aithru-agent/trace
```

- [ ] **Step 2: Update no-Python check scan paths**

In `backend/scripts/check-no-python.mjs`, replace:

```js
const DEFAULT_RELATIVE_PATHS = ["src", "examples", "scripts", "package.json"];
```

with:

```js
const DEFAULT_RELATIVE_PATHS = [
  "apps",
  "packages",
  "examples",
  "scripts",
  "package.json",
];
```

- [ ] **Step 3: Update active docs**

Replace active documentation path references:

```txt
backend/src/api -> backend/apps/api/src
backend/src/application/runtime.ts -> backend/apps/api/src/runtime.ts
backend/src/contracts -> backend/packages/contracts/src
backend/src/core -> backend/packages/harness/src
backend/src/capabilities -> backend/packages/capabilities/src
backend/src/model -> backend/packages/model/src
backend/src/persistence -> backend/packages/persistence/src
backend/src/stream -> backend/packages/stream/src
backend/src/trace -> backend/packages/trace/src
backend/src/worker -> backend/packages/worker/src
backend/src/skills -> backend/packages/skills/src
backend/src/memory -> backend/packages/memory/src
backend/src/snapshots -> backend/packages/snapshots/src
backend/src/subagent -> backend/packages/subagents/src
```

The active backend layout block in `README.md`, `AGENTS.md`, `docs/00-agent-harness-design.md`, and `docs/ARCHITECTURE.md` should show `apps/api` and `packages/*`, not `src/*`.

- [ ] **Step 4: Assert old source tree is gone**

Run:

```powershell
Test-Path backend/src
```

Expected: `False`. If it returns `True`, inspect it with:

```powershell
Get-ChildItem -Recurse backend/src
```

Only remove it if it is empty:

```powershell
Remove-Item backend/src -Recurse
```

- [ ] **Step 5: Verify there are no stale source-path imports**

Run:

```bash
cd backend
rg -n "../../src|../src|backend/src|from \"../contracts|from \"../stream|from \"../capabilities|from \"../persistence|from \"../core|from \"../model" apps packages tests examples scripts
```

Expected: no matches.

- [ ] **Step 6: Run full verification**

Run:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
npx tsx examples/approval_demo.ts
```

Expected:

```txt
typecheck exits 0
29 test files pass
130 tests pass
check:no-python-backend PASSED
file report example prints "All required events present."
approval demo reaches "Run status: completed"
```

- [ ] **Step 7: Smoke-test local server**

Run:

```powershell
cd backend
$env:PORT="8011"
$p = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d","/s","/c","npm run dev") -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8011/api/health
Stop-Process -Id $p.Id -Force
```

Expected response body:

```json
{"status":"ok","version":"0.1.0"}
```

- [ ] **Step 8: Commit**

```bash
git add backend README.md AGENTS.md docs
git commit -m "docs(backend): align package workspace structure"
```

---

## Final Verification

After all tasks are complete, run:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
npx tsx examples/approval_demo.ts
```

Then run:

```bash
rg -n "backend-ts|backend/src|../../src|../src" README.md AGENTS.md docs backend --glob "!node_modules/**" --glob "!dist/**"
```

Expected:

- No `backend-ts` matches.
- No active `backend/src` layout references.
- No test/example imports from `../../src` or `../src`.
- All verification commands exit 0.

## Self-Review Notes

- Spec coverage: Tasks cover workspace package manifests, app/package layout, package imports, docs, examples, scripts, no-Python check, and full verification.
- Scope: Single structural migration, no behavior changes.
- Type consistency: Package names match the accepted spec: `@aithru-agent/contracts`, `@aithru-agent/stream`, `@aithru-agent/capabilities`, `@aithru-agent/harness`, `@aithru-agent/worker`, and related packages.
- Known execution note: Because current local workspace already contains an uncommitted `backend-ts -> backend` rename, implementation should continue using `backend/` paths and avoid recreating `backend-ts/`.
