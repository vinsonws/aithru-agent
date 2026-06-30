import type { SkillPackage } from "./loader.js";
import type { SkillRegistry } from "./registry.js";

export interface SkillDocumentStore {
  getDocument(kind: string, id: string): { payload: unknown } | undefined;
  listDocuments(kind: string): { payload: unknown }[];
}

export interface ResolvedSkill {
  key: string;
  name: string;
  description: string | null;
  instructions: string;
  allowed_tools: string[];
  denied_tools: string[];
  source: "builtin" | "user" | "registry";
  version: string;
  status: string;
  enabled: boolean;
}

export interface SkillCatalogEntry {
  key: string;
  name: string;
  description: string | null;
  source: ResolvedSkill["source"];
  version: string;
}

interface SkillEntryPayload {
  key?: string;
  name?: string;
  description?: string | null;
  version?: string;
  status?: string;
  enabled?: boolean;
  configuration?: {
    instructions?: string;
    allowed_tools?: string[];
    denied_tools?: string[];
  } | null;
  instructions?: string;
  allowed_tools?: string[];
  denied_tools?: string[];
}

export class SkillResolver {
  constructor(
    private builtins: SkillRegistry,
    private store: SkillDocumentStore,
  ) {}

  resolve(skillId: string, orgId: string, actorUserId: string): ResolvedSkill | null {
    const userDoc = this.store.getDocument("skill_package_user", `${orgId}:${actorUserId}:${skillId}`);
    const userSkill = userDoc?.payload as SkillEntryPayload | undefined;
    const builtin = this.builtins.get(skillId);
    const regEntry = this.findRegistryEntry(orgId, skillId);

    let base: ResolvedSkill;
    if (userSkill) {
      base = fromEntry(userSkill, skillId, "user");
    } else if (builtin) {
      base = fromPackage(builtin, "builtin");
    } else if (regEntry) {
      base = fromEntry(regEntry, skillId, "registry");
    } else {
      return null;
    }

    if (regEntry) {
      if (typeof regEntry.enabled === "boolean") base.enabled = regEntry.enabled;
      if (typeof regEntry.status === "string") base.status = regEntry.status;
    }

    if (!base.enabled || base.status !== "published") return null;
    return base;
  }

  listVisible(orgId: string, actorUserId: string): SkillCatalogEntry[] {
    const keys = new Set<string>();
    for (const pkg of this.builtins.list()) keys.add(pkg.key);
    for (const doc of this.store.listDocuments("skill_registry_entry")) {
      const entry = doc.payload as SkillEntryPayload;
      if ((entry as any).org_id === orgId && entry.key) keys.add(entry.key);
    }
    for (const doc of this.store.listDocuments("skill_package_user")) {
      const entry = doc.payload as SkillEntryPayload;
      if ((entry as any).org_id === orgId && (entry as any).owner_user_id === actorUserId && entry.key) {
        keys.add(entry.key);
      }
    }
    return [...keys]
      .map((key) => this.resolve(key, orgId, actorUserId))
      .filter((skill): skill is ResolvedSkill => skill !== null)
      .map(skillCatalogEntry);
  }

  private findRegistryEntry(orgId: string, key: string): SkillEntryPayload | undefined {
    const byId = this.store.getDocument("skill_registry_entry", key)?.payload as SkillEntryPayload | undefined;
    if (byId && (byId as any).org_id === orgId) return byId;
    return this.store
      .listDocuments("skill_registry_entry")
      .map((doc) => doc.payload as SkillEntryPayload)
      .find((entry) => (entry as any).org_id === orgId && entry.key === key);
  }
}

export function skillCatalogEntry(skill: ResolvedSkill): SkillCatalogEntry {
  return {
    key: skill.key,
    name: skill.name,
    description: skill.description,
    source: skill.source,
    version: skill.version,
  };
}

function fromPackage(pkg: SkillPackage, source: ResolvedSkill["source"]): ResolvedSkill {
  return {
    key: pkg.key,
    name: pkg.name,
    description: pkg.description,
    instructions: pkg.instructions,
    allowed_tools: pkg.allowed_tools,
    denied_tools: pkg.denied_tools,
    version: pkg.version,
    status: pkg.status,
    enabled: pkg.enabled,
    source,
  };
}

function fromEntry(entry: SkillEntryPayload, fallbackKey: string, source: ResolvedSkill["source"]): ResolvedSkill {
  const cfg = entry.configuration ?? {};
  return {
    key: entry.key ?? fallbackKey,
    name: entry.name ?? fallbackKey,
    description: entry.description ?? null,
    instructions: cfg.instructions ?? entry.instructions ?? "",
    allowed_tools: cfg.allowed_tools ?? entry.allowed_tools ?? [],
    denied_tools: cfg.denied_tools ?? entry.denied_tools ?? [],
    version: entry.version ?? "0.0.0",
    status: entry.status ?? "published",
    enabled: entry.enabled ?? true,
    source,
  };
}
