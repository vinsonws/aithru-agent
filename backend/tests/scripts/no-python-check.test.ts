import { mkdtempSync, mkdirSync, rmSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

type NoPythonCheckModule = {
  scanForPythonBackendViolations: (options: {
    rootDir: string;
    relativePaths: string[];
  }) => Array<{ file: string; line: number; pattern: string }>;
};

const noPythonCheckModuleUrl = new URL(
  "../../scripts/check-no-python.mjs",
  import.meta.url,
).href;

async function loadNoPythonCheckModule(): Promise<NoPythonCheckModule> {
  return (await import(/* @vite-ignore */ noPythonCheckModuleUrl)) as NoPythonCheckModule;
}

describe("check:no-python-backend", () => {
  it("uses a cross-platform Node entrypoint", () => {
    const packageJson = JSON.parse(
      readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
    ) as { scripts: Record<string, string> };

    expect(packageJson.scripts["check:no-python-backend"]).toBe(
      "node scripts/check-no-python.mjs",
    );
    expect(
      existsSync(new URL("../../scripts/check-no-python.mjs", import.meta.url)),
    ).toBe(true);
  });

  it("detects Python backend process references without requiring bash", async () => {
    const { scanForPythonBackendViolations } = await loadNoPythonCheckModule();

    const root = mkdtempSync(join(tmpdir(), "aithru-no-python-"));
    try {
      mkdirSync(join(root, "src"), { recursive: true });
      writeFileSync(
        join(root, "src", "bad.ts"),
        "export const cmd = 'uv run python examples/file_report_agent.py';\n",
      );

      const violations = scanForPythonBackendViolations({
        rootDir: root,
        relativePaths: ["src"],
      });

      expect(violations).toHaveLength(1);
      expect(violations[0]).toMatchObject({
        file: "src/bad.ts",
        line: 1,
      });
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("ignores guard names and explanatory comments that do not start Python", async () => {
    const { scanForPythonBackendViolations } = await loadNoPythonCheckModule();

    const root = mkdtempSync(join(tmpdir(), "aithru-no-python-"));
    try {
      mkdirSync(join(root, "examples"), { recursive: true });
      writeFileSync(
        join(root, "package.json"),
        '{ "scripts": { "check:no-python-backend": "node scripts/check-no-python.mjs" } }\n',
      );
      writeFileSync(
        join(root, "examples", "notes.ts"),
        "// same shape as Python output\nexport const ok = true;\n",
      );

      const violations = scanForPythonBackendViolations({
        rootDir: root,
        relativePaths: ["package.json", "examples"],
      });

      expect(violations).toEqual([]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("ignores generated Python caches", async () => {
    const { scanForPythonBackendViolations } = await loadNoPythonCheckModule();

    const root = mkdtempSync(join(tmpdir(), "aithru-no-python-"));
    try {
      mkdirSync(join(root, "examples", "__pycache__"), { recursive: true });
      writeFileSync(
        join(root, "examples", "__pycache__", "file_report_agent.cpython-312.pyc"),
        "aithru_agent.api.main",
      );

      const violations = scanForPythonBackendViolations({
        rootDir: root,
        relativePaths: ["examples"],
      });

      expect(violations).toEqual([]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
