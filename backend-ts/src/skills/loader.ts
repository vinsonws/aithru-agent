// backend-ts/src/skills/loader.ts

import { readFileSync, existsSync } from "fs";
import { join } from "path";

export interface SkillPackage {
  name: string;
  path: string;
  instructions: string;
  metadata: Record<string, string>;
}

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

  private parseSkillMd(filePath: string, content: string): SkillPackage {
    const name = filePath.split("/").slice(-2, -1)[0] || "unknown";
    const metadata: Record<string, string> = {};

    // Extract frontmatter if present
    const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    if (match) {
      for (const line of match[1].split("\n")) {
        const [key, ...vals] = line.split(":");
        if (key && vals.length) metadata[key.trim()] = vals.join(":").trim();
      }
      content = match[2];
    }

    return { name, path: filePath, instructions: content.trim(), metadata };
  }
}
