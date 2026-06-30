import { readFileSync, existsSync, readdirSync, statSync } from "fs";
import { join, basename } from "path";

export interface SkillResourceIndex {
  references: string[];
  scripts: string[];
  assets: string[];
  examples: string[];
}

export interface SkillPackage {
  key: string;
  path: string;
  name: string;
  description: string | null;
  version: string;
  status: string;
  enabled: boolean;
  allowed_tools: string[];
  denied_tools: string[];
  instructions: string;
  resources: SkillResourceIndex;
}

const RESOURCE_DIRS: Array<keyof SkillResourceIndex> = ["references", "scripts", "assets", "examples"];

export class SkillLoader {
  loadFromFile(skillPath: string): SkillPackage | null {
    if (!existsSync(skillPath)) return null;
    const content = readFileSync(skillPath, "utf-8");
    return this.parseSkillMd(skillPath, content);
  }

  loadFromDir(dirPath: string): SkillPackage[] {
    const skillFile = join(dirPath, "SKILL.md");
    const pkg = this.loadFromFile(skillFile);
    return pkg ? [pkg] : [];
  }

  loadBuiltinPackages(rootDir: string): SkillPackage[] {
    if (!existsSync(rootDir)) return [];
    return readdirSync(rootDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .flatMap((entry) => this.loadFromDir(join(rootDir, entry.name)));
  }

  private parseSkillMd(filePath: string, content: string): SkillPackage {
    const dirPath = join(filePath, "..");
    const key = basename(dirPath);
    const { frontmatter, body } = splitFrontmatter(content);
    const fm = parseFrontmatter(frontmatter);

    return {
      key,
      path: dirPath,
      name: stringValue(fm.name) ?? key,
      description: stringValue(fm.description),
      version: stringValue(fm.version) ?? "0.0.0",
      status: stringValue(fm.status) ?? "published",
      enabled: fm.enabled == null ? true : Boolean(fm.enabled),
      allowed_tools: stringArray(fm.allowed_tools),
      denied_tools: stringArray(fm.denied_tools),
      instructions: body.trim(),
      resources: indexResources(dirPath),
    };
  }
}

export function findBuiltinSkillsRoot(): string | null {
  for (const candidate of [
    join(process.cwd(), "packages", "skills", "builtin_packages"),
    join(process.cwd(), "backend", "packages", "skills", "builtin_packages"),
  ]) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

function splitFrontmatter(content: string): { frontmatter: string; body: string } {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!match) return { frontmatter: "", body: content };
  return { frontmatter: match[1], body: match[2] };
}

function indexResources(dirPath: string): SkillResourceIndex {
  const result: SkillResourceIndex = { references: [], scripts: [], assets: [], examples: [] };
  for (const dir of RESOURCE_DIRS) {
    const dirAbs = join(dirPath, dir);
    if (!existsSync(dirAbs) || !statSync(dirAbs).isDirectory()) continue;
    result[dir] = readdirSync(dirAbs)
      .filter((entry) => {
        const stat = statSync(join(dirAbs, entry));
        return stat.isFile();
      })
      .sort();
  }
  return result;
}

// ── Minimal YAML frontmatter parser ──────────────────────────────────
// Handles: scalars, block sequences (- item), flow sequences ([a, b]),
// folded (>) and literal (|) block scalars with chomping (-/+).

type YamlValue = string | string[] | boolean | number | null;

function parseFrontmatter(text: string): Record<string, YamlValue> {
  const result: Record<string, YamlValue> = {};
  if (!text.trim()) return result;
  const lines = text.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim() || line.trim().startsWith("#")) {
      i += 1;
      continue;
    }
    const match = line.match(/^(\S[^:]*):\s*(.*)$/);
    if (!match) {
      i += 1;
      continue;
    }
    const key = match[1];
    const rest = match[2];
    if (rest === "") {
      const [value, nextI] = parseBlockValue(lines, i + 1);
      result[key] = value;
      i = nextI;
    } else if (rest === ">" || rest === ">-" || rest === ">+" || rest === "|" || rest === "|-" || rest === "|+") {
      const [value, nextI] = parseBlockScalar(lines, i + 1, rest);
      result[key] = value;
      i = nextI;
    } else if (rest.startsWith("[") && rest.endsWith("]")) {
      result[key] = parseFlowArray(rest);
      i += 1;
    } else {
      result[key] = parseScalar(rest);
      i += 1;
    }
  }
  return result;
}

function parseBlockValue(lines: string[], start: number): [YamlValue, number] {
  const items: string[] = [];
  let i = start;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      i += 1;
      continue;
    }
    const itemMatch = line.match(/^\s+-\s+(.*)$/);
    if (!itemMatch) break;
    items.push(stripQuotes(itemMatch[1].trim()));
    i += 1;
  }
  if (items.length === 0) return [null, start];
  return [items, i];
}

function parseBlockScalar(lines: string[], start: number, indicator: string): [string, number] {
  const folded = indicator.startsWith(">");
  const chomp = indicator.endsWith("-") ? "strip" : indicator.endsWith("+") ? "keep" : "clip";
  const collected: string[] = [];
  let i = start;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      collected.push("");
      i += 1;
      continue;
    }
    if (/^\S/.test(line)) break;
    collected.push(line.replace(/^\s{2}/, ""));
    i += 1;
  }
  while (collected.length > 0 && collected[collected.length - 1] === "") {
    collected.pop();
  }
  let value: string;
  if (folded) {
    value = collected.join("\n").replace(/\n+/g, " ");
  } else {
    value = collected.join("\n");
  }
  if (chomp === "clip") value += "\n";
  else if (chomp === "keep") value += "\n";
  return [value.trimEnd(), i];
}

function parseFlowArray(text: string): string[] {
  const inner = text.slice(1, -1).trim();
  if (!inner) return [];
  return inner.split(",").map((item) => stripQuotes(item.trim())).filter(Boolean);
}

function parseScalar(text: string): YamlValue {
  const trimmed = text.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (trimmed === "null" || trimmed === "~") return null;
  if (/^-?\d+$/.test(trimmed)) return Number(trimmed);
  return stripQuotes(trimmed);
}

function stripQuotes(text: string): string {
  if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
    return text.slice(1, -1);
  }
  return text;
}

function stringValue(value: YamlValue): string | null {
  if (typeof value === "string") return value;
  if (value == null) return null;
  return String(value);
}

function stringArray(value: YamlValue): string[] {
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === "string");
  if (typeof value === "string") {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [];
}
