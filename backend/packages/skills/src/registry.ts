import { SkillLoader, type SkillPackage } from "./loader.js";

export class SkillRegistry {
  private skills = new Map<string, SkillPackage>();
  private loader = new SkillLoader();

  register(pkg: SkillPackage): void {
    this.skills.set(pkg.name, pkg);
  }

  get(name: string): SkillPackage | undefined {
    return this.skills.get(name);
  }

  list(): SkillPackage[] {
    return [...this.skills.values()];
  }

  loadFromDir(dirPath: string): void {
    const packages = this.loader.loadFromDir(dirPath);
    for (const pkg of packages) {
      this.register(pkg);
    }
  }
}
