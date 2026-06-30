import { describe, it, expect } from "vitest";
import { InMemoryStore } from "@aithru-agent/persistence";
import { SkillLoader, SkillRegistry, SkillResolver, findBuiltinSkillsRoot } from "@aithru-agent/skills";
import { writeFileSync, mkdirSync, rmSync, readdirSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";

function makeDir(): string {
  const dir = join(tmpdir(), `skill_test_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

describe("SkillLoader", () => {
  const loader = new SkillLoader();

  it("loads a SKILL.md file without frontmatter", () => {
    const dir = makeDir();
    try {
      const skillPath = join(dir, "SKILL.md");
      writeFileSync(skillPath, "# My Skill\n\nInstructions here.\n");

      const pkg = loader.loadFromFile(skillPath);
      expect(pkg).not.toBeNull();
      expect(pkg!.instructions).toBe("# My Skill\n\nInstructions here.");
      expect(pkg!.name).toBe(pkg!.key);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("loads a SKILL.md file with scalar frontmatter", () => {
    const dir = makeDir();
    try {
      const skillPath = join(dir, "SKILL.md");
      writeFileSync(
        skillPath,
        "---\nname: My Skill\nversion: 1.0\n---\n# Skill Body\n\nActual instructions.",
      );

      const pkg = loader.loadFromFile(skillPath);
      expect(pkg).not.toBeNull();
      expect(pkg!.key).toBe(dir.split("/").pop()!);
      expect(pkg!.name).toBe("My Skill");
      expect(pkg!.version).toBe("1.0");
      expect(pkg!.instructions).toBe("# Skill Body\n\nActual instructions.");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("parses folded multiline description (>-)", () => {
    const dir = makeDir();
    try {
      const skillPath = join(dir, "SKILL.md");
      writeFileSync(
        skillPath,
        [
          "---",
          "name: Bootstrap",
          "description: >-",
          "  Generate a personalized AI partner identity through a warm, adaptive onboarding conversation.",
          "  Trigger when the user wants to create, set up, or initialize their AI partner's",
          "  identity.",
          "---",
          "# Bootstrap",
          "",
          "Body text.",
        ].join("\n"),
      );

      const pkg = loader.loadFromFile(skillPath);
      expect(pkg).not.toBeNull();
      expect(pkg!.description).toBe(
        "Generate a personalized AI partner identity through a warm, adaptive onboarding conversation. Trigger when the user wants to create, set up, or initialize their AI partner's identity.",
      );
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("parses allowed_tools as a YAML block array", () => {
    const dir = makeDir();
    try {
      const skillPath = join(dir, "SKILL.md");
      writeFileSync(
        skillPath,
        [
          "---",
          "name: Restricted Skill",
          "allowed_tools:",
          "  - workspace.read_file",
          "  - workspace.list_files",
          "denied_tools:",
          "  - workspace.delete_file",
          "---",
          "# Body",
        ].join("\n"),
      );

      const pkg = loader.loadFromFile(skillPath);
      expect(pkg).not.toBeNull();
      expect(pkg!.allowed_tools).toEqual(["workspace.read_file", "workspace.list_files"]);
      expect(pkg!.denied_tools).toEqual(["workspace.delete_file"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("parses allowed_tools as a YAML flow array", () => {
    const dir = makeDir();
    try {
      const skillPath = join(dir, "SKILL.md");
      writeFileSync(
        skillPath,
        "---\nname: Flow Skill\nallowed_tools: [workspace.read_file, workspace.write_file]\n---\n# Body\n",
      );

      const pkg = loader.loadFromFile(skillPath);
      expect(pkg).not.toBeNull();
      expect(pkg!.allowed_tools).toEqual(["workspace.read_file", "workspace.write_file"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("parses status and enabled fields", () => {
    const dir = makeDir();
    try {
      const skillPath = join(dir, "SKILL.md");
      writeFileSync(
        skillPath,
        "---\nname: Draft Skill\nstatus: draft\nenabled: false\n---\n# Body\n",
      );

      const pkg = loader.loadFromFile(skillPath);
      expect(pkg).not.toBeNull();
      expect(pkg!.status).toBe("draft");
      expect(pkg!.enabled).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("defaults status to published and enabled to true", () => {
    const dir = makeDir();
    try {
      const skillPath = join(dir, "SKILL.md");
      writeFileSync(skillPath, "---\nname: Default Skill\n---\n# Body\n");

      const pkg = loader.loadFromFile(skillPath);
      expect(pkg).not.toBeNull();
      expect(pkg!.status).toBe("published");
      expect(pkg!.enabled).toBe(true);
      expect(pkg!.version).toBe("0.0.0");
      expect(pkg!.allowed_tools).toEqual([]);
      expect(pkg!.denied_tools).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("returns null for nonexistent file", () => {
    const pkg = loader.loadFromFile("/nonexistent/skill.md");
    expect(pkg).toBeNull();
  });

  it("loads from directory", () => {
    const dir = makeDir();
    try {
      writeFileSync(join(dir, "SKILL.md"), "# Dir Skill\n\nContent.");

      const packages = loader.loadFromDir(dir);
      expect(packages.length).toBe(1);
      expect(packages[0].instructions).toBe("# Dir Skill\n\nContent.");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("returns empty array for directory without SKILL.md", () => {
    const dir = makeDir();
    try {
      const packages = loader.loadFromDir(dir);
      expect(packages).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("discovers all skill directories under builtin_packages root", () => {
    const root = makeDir();
    try {
      mkdirSync(join(root, "alpha"));
      mkdirSync(join(root, "beta"));
      mkdirSync(join(root, "not-a-skill"));
      writeFileSync(join(root, "alpha", "SKILL.md"), "---\nname: Alpha\n---\n# Alpha\n");
      writeFileSync(join(root, "beta", "SKILL.md"), "---\nname: Beta\n---\n# Beta\n");

      const packages = loader.loadBuiltinPackages(root);
      expect(packages.length).toBe(2);
      const keys = packages.map((p) => p.key).sort();
      expect(keys).toEqual(["alpha", "beta"]);
      expect(packages.find((p) => p.key === "alpha")!.name).toBe("Alpha");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("indexes optional resource directories without executing them", () => {
    const dir = makeDir();
    try {
      writeFileSync(join(dir, "SKILL.md"), "---\nname: Res Skill\n---\n# Body\n");
      mkdirSync(join(dir, "references"));
      writeFileSync(join(dir, "references", "guide.md"), "# Guide");
      mkdirSync(join(dir, "scripts"));
      writeFileSync(join(dir, "scripts", "helper.sh"), "#!/bin/sh\necho hi");
      mkdirSync(join(dir, "assets"));
      writeFileSync(join(dir, "assets", "logo.svg"), "<svg/>");
      mkdirSync(join(dir, "examples"));
      writeFileSync(join(dir, "examples", "example.md"), "# Example");

      const pkg = loader.loadFromDir(dir)[0];
      expect(pkg.resources.references).toEqual(["guide.md"]);
      expect(pkg.resources.scripts).toEqual(["helper.sh"]);
      expect(pkg.resources.assets).toEqual(["logo.svg"]);
      expect(pkg.resources.examples).toEqual(["example.md"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("has empty resource arrays when no resource dirs exist", () => {
    const dir = makeDir();
    try {
      writeFileSync(join(dir, "SKILL.md"), "# Body\n");
      const pkg = loader.loadFromDir(dir)[0];
      expect(pkg.resources.references).toEqual([]);
      expect(pkg.resources.scripts).toEqual([]);
      expect(pkg.resources.assets).toEqual([]);
      expect(pkg.resources.examples).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("SkillRegistry", () => {
  it("loads builtin packages and indexes by key", () => {
    const root = makeDir();
    try {
      mkdirSync(join(root, "find-skills"));
      writeFileSync(join(root, "find-skills", "SKILL.md"), "---\nname: Find Skills\n---\n# Find\n");
      mkdirSync(join(root, "deep-research"));
      writeFileSync(join(root, "deep-research", "SKILL.md"), "---\nname: Deep Research\n---\n# Research\n");

      const registry = new SkillRegistry();
      registry.loadBuiltinPackages(root);

      expect(registry.get("find-skills")?.name).toBe("Find Skills");
      expect(registry.get("deep-research")?.name).toBe("Deep Research");
      expect(registry.list().length).toBe(2);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});

describe("SkillResolver", () => {
  it("lists visible skill catalog without instructions", () => {
    const registry = new SkillRegistry();
    registry.register({
      key: "catalog-skill",
      path: "/skills/catalog-skill",
      name: "Catalog Skill",
      description: "Visible metadata.",
      version: "1.0.0",
      status: "published",
      enabled: true,
      allowed_tools: [],
      denied_tools: [],
      instructions: "secret body",
      resources: { references: [], scripts: [], assets: [], examples: [] },
    });
    const resolver = new SkillResolver(registry, new InMemoryStore());

    expect(resolver.listVisible("org_1", "user_1")).toEqual([{
      key: "catalog-skill",
      name: "Catalog Skill",
      description: "Visible metadata.",
      source: "builtin",
      version: "1.0.0",
    }]);
  });
});

describe("findBuiltinSkillsRoot", () => {
  it("locates the real builtin_packages directory", () => {
    const root = findBuiltinSkillsRoot();
    expect(root).not.toBeNull();
    const entries = readdirSync(root!, { withFileTypes: true })
      .filter((e) => e.isDirectory())
      .map((e) => e.name);
    expect(entries).toEqual(expect.arrayContaining(["deep-research", "skill-creator", "find-skills"]));
  });
});
