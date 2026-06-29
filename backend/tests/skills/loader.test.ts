import { describe, it, expect } from "vitest";
import { SkillLoader } from "@aithru-agent/skills";
import { writeFileSync, mkdirSync, rmSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";

describe("SkillLoader", () => {
  const loader = new SkillLoader();

  it("loads a SKILL.md file without frontmatter", () => {
    const dir = join(tmpdir(), `skill_test_${Date.now()}`);
    mkdirSync(dir, { recursive: true });
    try {
      const skillPath = join(dir, "SKILL.md");
      writeFileSync(skillPath, "# My Skill\n\nInstructions here.\n");

      const pkg = loader.loadFromFile(skillPath);
      expect(pkg).toBeDefined();
      expect(pkg!.instructions).toBe("# My Skill\n\nInstructions here.");
      expect(pkg!.metadata).toEqual({});
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("loads a SKILL.md file with frontmatter", () => {
    const dir = join(tmpdir(), `test-skill`);
    mkdirSync(dir, { recursive: true });
    try {
      const skillPath = join(dir, "SKILL.md");
      writeFileSync(
        skillPath,
        "---\ntitle: My Skill\nversion: 1.0\n---\n# Skill Body\n\nActual instructions.",
      );

      const pkg = loader.loadFromFile(skillPath);
      expect(pkg).toBeDefined();
      // name comes from the parent directory name (uses "/" split)
      expect(pkg!.name).toBe("test-skill");
      expect(pkg!.metadata).toEqual({ title: "My Skill", version: "1.0" });
      expect(pkg!.instructions).toBe("# Skill Body\n\nActual instructions.");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("returns null for nonexistent file", () => {
    const pkg = loader.loadFromFile("/nonexistent/skill.md");
    expect(pkg).toBeNull();
  });

  it("loads from directory", () => {
    const dir = join(tmpdir(), `skill_dir_${Date.now()}`);
    mkdirSync(dir, { recursive: true });
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
    const dir = join(tmpdir(), `empty_dir_${Date.now()}`);
    mkdirSync(dir, { recursive: true });
    try {
      const packages = loader.loadFromDir(dir);
      expect(packages).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
