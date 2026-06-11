import { describe, expect, it } from "vitest";
import type {
  AgentToolDescriptor,
  AgentToolKind,
  AgentToolCallResult,
} from "../src/index.js";

describe("Agent tool contracts", () => {
  it("allows only local tools and workflow capabilities", () => {
    const localKind: AgentToolKind = "local_tool";
    const workflowKind: AgentToolKind = "workflow_capability";

    expect(localKind).toBe("local_tool");
    expect(workflowKind).toBe("workflow_capability");
  });

  it("supports workflow capability metadata and external run references", () => {
    const descriptor = {
      name: "workflow.http_download",
      description: "Download a URL through the Workflow product.",
      kind: "workflow_capability",
      requiredScopes: ["workflow.capability.invoke.http_download"],
      riskLevel: "read",
      approvalPolicy: "on_risk",
      metadata: {
        capabilityKey: "http_download",
        capabilityVersion: "0.1.0",
        externalApprovalOwner: "workflow",
      },
    } satisfies AgentToolDescriptor;

    const result = {
      id: "tool_1" as AgentToolCallResult["id"],
      toolName: descriptor.name,
      status: "waiting_approval",
      redaction: "partial",
      externalRun: {
        kind: "workflow_capability",
        capabilityKey: "http_download",
        capabilityRunId: "caprun_1",
        status: "waiting_approval",
        approvalId: "capapproval_1",
        correlationId: "corr_1",
      },
    } satisfies AgentToolCallResult;

    expect(result.externalRun?.approvalId).toBe("capapproval_1");
  });

  it("rejects removed production tool kinds at type level", () => {
    // @ts-expect-error core_node is intentionally not an Agent production tool kind.
    const removedKind: AgentToolKind = "core_node";
    expect(removedKind).toBe("core_node");
  });
});
