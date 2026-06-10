import { describe, it, expect } from "vitest";
import {
  parseSkillManifest,
  validateSkillManifest,
  createSkillFromManifest,
} from "../src/index.js";
import type { AgentSkillManifest } from "../src/index.js";
import type { OrgId } from "@aithru/agent-core";

const validManifest: AgentSkillManifest = {
  key: "test-skill",
  name: "Test Skill",
  version: "1.0.0",
  instructions: "This is a test skill.",
};

describe("validateSkillManifest", () => {
  it("should pass a valid manifest", () => {
    const result = validateSkillManifest(validManifest);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it("should fail when key is missing", () => {
    const result = validateSkillManifest({ ...validManifest, key: "" });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.field === "key")).toBe(true);
  });

  it("should fail when name is missing", () => {
    const result = validateSkillManifest({ ...validManifest, name: "" });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.field === "name")).toBe(true);
  });

  it("should fail when version is missing", () => {
    const result = validateSkillManifest({ ...validManifest, version: "" });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.field === "version")).toBe(true);
  });

  it("should fail when instructions is missing", () => {
    const result = validateSkillManifest({ ...validManifest, instructions: "" });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.field === "instructions")).toBe(true);
  });

  it("should fail with multiple missing fields", () => {
    const result = validateSkillManifest({} as AgentSkillManifest);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThanOrEqual(4);
  });

  it("should validate allowedTools is an array if present", () => {
    const result = validateSkillManifest({
      ...validManifest,
      allowedTools: "not-array" as unknown as string[],
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.field === "allowedTools")).toBe(true);
  });
});

describe("parseSkillManifest", () => {
  it("should parse a valid object", () => {
    const result = parseSkillManifest(validManifest);
    expect(result.key).toBe("test-skill");
  });

  it("should throw on null input", () => {
    expect(() => parseSkillManifest(null)).toThrow("non-null object");
  });

  it("should throw on non-object input", () => {
    expect(() => parseSkillManifest("string")).toThrow("non-null object");
  });
});

describe("createSkillFromManifest", () => {
  it("should create AgentSkill from valid manifest", () => {
    const orgId = "org_1" as OrgId;
    const skill = createSkillFromManifest(validManifest, orgId);

    expect(skill.key).toBe("test-skill");
    expect(skill.name).toBe("Test Skill");
    expect(skill.orgId).toBe(orgId);
    expect(skill.version).toBe("1.0.0");
    expect(skill.instructions).toBe("This is a test skill.");
    expect(skill.allowedTools).toEqual([]);
    expect(skill.allowedSubagents).toEqual([]);
    expect(skill.status).toBe("draft");
  });

  it("should throw on invalid manifest", () => {
    expect(() =>
      createSkillFromManifest({} as AgentSkillManifest, "org_1" as OrgId),
    ).toThrow("Invalid skill manifest");
  });

  it("should preserve optional fields", () => {
    const manifest: AgentSkillManifest = {
      ...validManifest,
      description: "A test",
      whenToUse: "When testing",
      allowedTools: ["workspace.readFile", "workspace.writeFile"],
      allowedSubagents: ["researcher"],
      status: "published",
      inputSchema: { type: "object" },
    };

    const skill = createSkillFromManifest(manifest, "org_1" as OrgId);
    expect(skill.description).toBe("A test");
    expect(skill.whenToUse).toBe("When testing");
    expect(skill.allowedTools).toHaveLength(2);
    expect(skill.allowedSubagents).toHaveLength(1);
    expect(skill.status).toBe("published");
    expect(skill.inputSchema).toEqual({ type: "object" });
  });
});
