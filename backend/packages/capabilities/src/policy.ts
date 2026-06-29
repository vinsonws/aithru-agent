import type { AgentToolDescriptor, AgentToolCallRequest } from "./descriptors.js";
import type { AgentRun } from "@aithru-agent/contracts";

export interface RunContext {
  run: AgentRun;
}

export interface ScopeCheckResult {
  allowed: boolean;
  missing_scopes: string[];
}

export function checkScopes(
  tool: AgentToolDescriptor,
  run: AgentRun,
): ScopeCheckResult {
  const userScopes = new Set(run.scopes);
  // "*" scope means unrestricted
  if (userScopes.has("*")) {
    return { allowed: true, missing_scopes: [] };
  }
  const missing = tool.required_scopes.filter((s) => !userScopes.has(s));
  return { allowed: missing.length === 0, missing_scopes: missing };
}

export interface SkillPolicy {
  allowedTools: Set<string>;
  deniedTools: Set<string>;
}

export function resolveSkillPolicy(
  skillConfigs: Array<{ allowed_tools?: string[]; denied_tools?: string[] }>,
): SkillPolicy {
  const allowedTools = new Set<string>();
  const deniedTools = new Set<string>();
  for (const config of skillConfigs) {
    for (const tool of config.allowed_tools || []) allowedTools.add(tool);
    for (const tool of config.denied_tools || []) deniedTools.add(tool);
  }
  return { allowedTools, deniedTools };
}

export interface PolicyCheckResult {
  allowed: boolean;
  requires_approval: boolean;
  reason?: string;
  audit_event_type?: string;
}

export class PolicyEngine {
  private skillPolicy: SkillPolicy;
  private run: AgentRun;

  constructor(skillPolicy: SkillPolicy, run: AgentRun) {
    this.skillPolicy = skillPolicy;
    this.run = run;
  }

  checkToolCall(
    tool: AgentToolDescriptor,
    req: AgentToolCallRequest,
  ): PolicyCheckResult {
    // 1. Skill allow/deny policy
    if (this.skillPolicy.deniedTools.has(req.name)) {
      return {
        allowed: false,
        requires_approval: false,
        reason: `Tool "${req.name}" denied by skill policy`,
        audit_event_type: "tool.skill_denied",
      };
    }
    if (
      this.skillPolicy.allowedTools.size > 0 &&
      !this.skillPolicy.allowedTools.has(req.name)
    ) {
      return {
        allowed: false,
        requires_approval: false,
        reason: `Tool "${req.name}" not in skill allow list`,
        audit_event_type: "tool.skill_denied",
      };
    }

    // 2. Scope check
    const scopeResult = checkScopes(tool, this.run);
    if (!scopeResult.allowed) {
      return {
        allowed: false,
        requires_approval: false,
        reason: `Missing scopes: ${scopeResult.missing_scopes.join(", ")}`,
        audit_event_type: "tool.scope_denied",
      };
    }

    // 3. Approval check. The wildcard scope is reserved for trusted internal
    // deterministic runs and examples; normal actor scopes still pause.
    const userScopes = new Set(this.run.scopes);
    const autoApproved =
      userScopes.has("*") ||
      (tool.auto_approve_scopes ?? []).some((scope) => userScopes.has(scope));

    return {
      allowed: true,
      requires_approval: tool.requires_approval && !autoApproved,
    };
  }
}
