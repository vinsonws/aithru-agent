import type { AgentSkill, OrgId } from "@aithru/agent-core";
import type { AgentSkillManifest } from "@aithru/agent-skills";

export interface AgentSkillResolver {
  resolve(skillIdOrKey: string): Promise<AgentSkill | null>;
  resolveFromManifest(manifest: AgentSkillManifest, orgId: OrgId): Promise<AgentSkill>;
}
