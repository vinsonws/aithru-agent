import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const DEFAULT_RELATIVE_PATHS = [
  "apps",
  "packages",
  "examples",
  "scripts",
  "package.json",
];
const SKIPPED_DIRECTORIES = new Set([
  ".git",
  "__pycache__",
  "coverage",
  "dist",
  "node_modules",
]);
const SKIPPED_EXTENSIONS = new Set([".pyc", ".pyo"]);
const SKIPPED_FILES = new Set([
  "scripts/check-no-python.mjs",
  "scripts/check-no-python.sh",
]);

const FORBIDDEN_PATTERNS = [
  {
    name: "python process",
    pattern: /(?:^|["'`:=\[(,{]\s*)(?:python3?(?:\.exe)?|uv\s+run)(?=\s|["'`,)\]}]|$)/,
  },
  { name: "python shebang", pattern: /^#!\/usr\/bin\/env python\b/i },
  { name: "Pydantic", pattern: /\bpydantic(?:[-_]ai)?\b/i },
  { name: "FastAPI", pattern: /\bfastapi\b/i },
  { name: "uvicorn", pattern: /\buvicorn\b/i },
  { name: "Python backend package", pattern: /\baithru_agent\./i },
];

function normalizePath(path) {
  return path.replace(/\\/g, "/");
}

function shouldSkipFile(path) {
  return SKIPPED_FILES.has(path) || SKIPPED_EXTENSIONS.has(extname(path));
}

function collectFiles(rootDir, relativePaths) {
  const files = [];

  for (const relativePath of relativePaths) {
    const absolutePath = join(rootDir, relativePath);
    if (!existsSync(absolutePath)) {
      continue;
    }

    const stats = statSync(absolutePath);
    if (stats.isDirectory()) {
      walkDirectory(rootDir, absolutePath, files);
    } else if (stats.isFile()) {
      const normalized = normalizePath(relative(rootDir, absolutePath));
      if (!shouldSkipFile(normalized)) {
        files.push(absolutePath);
      }
    }
  }

  return files;
}

function walkDirectory(rootDir, directory, files) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const absolutePath = join(directory, entry.name);
    if (entry.isDirectory()) {
      if (!SKIPPED_DIRECTORIES.has(entry.name)) {
        walkDirectory(rootDir, absolutePath, files);
      }
      continue;
    }

    if (!entry.isFile()) {
      continue;
    }

    const normalized = normalizePath(relative(rootDir, absolutePath));
    if (!shouldSkipFile(normalized)) {
      files.push(absolutePath);
    }
  }
}

export function scanForPythonBackendViolations(options = {}) {
  const rootDir = options.rootDir ?? process.cwd();
  const relativePaths = options.relativePaths ?? DEFAULT_RELATIVE_PATHS;
  const violations = [];

  for (const file of collectFiles(rootDir, relativePaths)) {
    const relativeFile = normalizePath(relative(rootDir, file));
    const lines = readFileSync(file, "utf8").split(/\r?\n/);

    lines.forEach((line, index) => {
      for (const forbidden of FORBIDDEN_PATTERNS) {
        if (forbidden.pattern.test(line)) {
          violations.push({
            file: relativeFile,
            line: index + 1,
            pattern: forbidden.name,
          });
        }
      }
    });
  }

  return violations;
}

function runCli() {
  const violations = scanForPythonBackendViolations();
  if (violations.length === 0) {
    console.log("check:no-python-backend PASSED");
    return 0;
  }

  console.error(
    `check:no-python-backend FAILED with ${violations.length} violation(s)`,
  );
  for (const violation of violations) {
    console.error(
      `${violation.file}:${violation.line} ${violation.pattern}`,
    );
  }
  return 1;
}

const currentScript = pathToFileURL(process.argv[1] ?? "").href;
if (import.meta.url === currentScript) {
  process.exitCode = runCli();
}
