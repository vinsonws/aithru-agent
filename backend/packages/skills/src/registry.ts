import { SkillLoader, type SkillPackage } from "./loader.js";

export class SkillRegistry {
  private skills = new Map<string, SkillPackage>();
  private loader = new SkillLoader();

  register(pkg: SkillPackage): void {
    this.skills.set(pkg.key, pkg);
  }

  get(key: string): SkillPackage | undefined {
    return this.skills.get(key);
  }

  list(): SkillPackage[] {
    return [...this.skills.values()];
  }

  loadFromDir(dirPath: string): void {
    for (const pkg of this.loader.loadFromDir(dirPath)) {
      this.register(pkg);
    }
  }

  loadBuiltinPackages(rootDir: string): void {
    for (const pkg of this.loader.loadBuiltinPackages(rootDir)) {
      this.register(pkg);
    }
  }
}
