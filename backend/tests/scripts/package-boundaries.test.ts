import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const backendRoot = fileURLToPath(new URL("../..", import.meta.url));

function tsFiles(relativeDir: string): string[] {
  const root = join(backendRoot, relativeDir);
  const files: string[] = [];

  function walk(dir: string) {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) {
        walk(path);
      } else if (path.endsWith(".ts")) {
        files.push(path);
      }
    }
  }

  walk(root);
  return files;
}

function packageImports(file: string): string[] {
  const contents = readFileSync(file, "utf8");
  return Array.from(contents.matchAll(/from\s+["'](@aithru-agent\/[^"']+)["']/g)).map(
    (match) => match[1],
  );
}

describe("backend package boundaries", () => {
  it("keeps model, stream, and capabilities imports inside their allowed layers", () => {
    const rules = [
      {
        dir: "packages/model/src",
        forbidden: [
          "@aithru-agent/api",
          "@aithru-agent/capabilities",
          "@aithru-agent/persistence",
          "@aithru-agent/worker",
        ],
      },
      {
        dir: "packages/stream/src",
        forbidden: [
          "@aithru-agent/api",
          "@aithru-agent/capabilities",
          "@aithru-agent/model",
          "@aithru-agent/persistence",
          "@aithru-agent/worker",
        ],
      },
      {
        dir: "packages/capabilities/src",
        forbidden: [
          "@aithru-agent/api",
          "@aithru-agent/model",
          "@aithru-agent/persistence",
          "@aithru-agent/worker",
        ],
      },
    ];

    const violations = rules.flatMap(({ dir, forbidden }) =>
      tsFiles(dir).flatMap((file) =>
        packageImports(file)
          .filter((importPath) => forbidden.includes(importPath))
          .map((importPath) => `${relative(backendRoot, file)} -> ${importPath}`),
      ),
    );

    expect(violations).toEqual([]);
  });
});
