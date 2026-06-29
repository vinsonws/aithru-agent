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
      "@aithru-agent/worker": resolve(root, "packages/worker/src/index.ts"),
    },
  },
  test: {
    globals: true,
    include: ["tests/**/*.test.ts"],
  },
});
