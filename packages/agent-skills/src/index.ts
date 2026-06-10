import type {
  AgentSkill,
  AgentSkillStatus,
  AgentWorkspacePolicy,
  AgentMemoryPolicy,
  AgentSandboxPolicy,
  AgentApprovalPolicy,
  SkillId,
  OrgId,
} from "@aithru/agent-core";

// ── Skill manifest ──────────────────────────────────────────────────────────

export type AgentSkillManifest = {
  key: string;
  name: string;
  description?: string;
  version: string;
  status?: "draft" | "published" | "deprecated";
  instructions: string;
  whenToUse?: string;
  allowedTools?: string[];
  allowedSubagents?: string[];
  workspacePolicy?: AgentWorkspacePolicy;
  memoryPolicy?: AgentMemoryPolicy;
  sandboxPolicy?: AgentSandboxPolicy;
  approvalPolicy?: AgentApprovalPolicy;
  inputSchema?: unknown;
  outputSchema?: unknown;
};

export type ValidationError = {
  field: string;
  message: string;
};

export type ValidationResult = {
  valid: boolean;
  errors: ValidationError[];
};

// ── Parser ──────────────────────────────────────────────────────────────────

export function parseSkillManifest(input: unknown): AgentSkillManifest {
  if (typeof input !== "object" || input === null) {
    throw new Error("Skill manifest must be a non-null object");
  }
  return input as AgentSkillManifest;
}

// ── Validator ───────────────────────────────────────────────────────────────

export function validateSkillManifest(
  manifest: AgentSkillManifest,
): ValidationResult {
  const errors: ValidationError[] = [];

  if (!manifest.key || typeof manifest.key !== "string") {
    errors.push({ field: "key", message: "key is required and must be a non-empty string" });
  }
  if (!manifest.name || typeof manifest.name !== "string") {
    errors.push({ field: "name", message: "name is required and must be a non-empty string" });
  }
  if (!manifest.version || typeof manifest.version !== "string") {
    errors.push({ field: "version", message: "version is required and must be a non-empty string" });
  }
  if (!manifest.instructions || typeof manifest.instructions !== "string") {
    errors.push({
      field: "instructions",
      message: "instructions is required and must be a non-empty string",
    });
  }

  if (manifest.allowedTools !== undefined && !Array.isArray(manifest.allowedTools)) {
    errors.push({ field: "allowedTools", message: "allowedTools must be an array of strings" });
  }
  if (manifest.allowedSubagents !== undefined && !Array.isArray(manifest.allowedSubagents)) {
    errors.push({
      field: "allowedSubagents",
      message: "allowedSubagents must be an array of strings",
    });
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

// ── Converter ───────────────────────────────────────────────────────────────

let skillIdCounter = 0;

export function createSkillFromManifest(
  manifest: AgentSkillManifest,
  orgId: OrgId,
): AgentSkill {
  const validation = validateSkillManifest(manifest);
  if (!validation.valid) {
    throw new Error(
      `Invalid skill manifest: ${validation.errors.map((e) => `${e.field}: ${e.message}`).join("; ")}`,
    );
  }

  skillIdCounter++;
  const id = `skill_${skillIdCounter}` as SkillId;

  const now = new Date().toISOString();

  return {
    id,
    orgId,
    key: manifest.key,
    name: manifest.name,
    description: manifest.description,
    instructions: manifest.instructions,
    whenToUse: manifest.whenToUse,
    allowedTools: manifest.allowedTools ?? [],
    allowedSubagents: manifest.allowedSubagents ?? [],
    workspacePolicy: manifest.workspacePolicy,
    memoryPolicy: manifest.memoryPolicy,
    sandboxPolicy: manifest.sandboxPolicy,
    approvalPolicy: manifest.approvalPolicy,
    inputSchema: manifest.inputSchema,
    outputSchema: manifest.outputSchema,
    version: manifest.version,
    status: (manifest.status as AgentSkillStatus) ?? "draft",
  };
}
