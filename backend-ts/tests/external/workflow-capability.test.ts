import { describe, expect, it } from "vitest";
import { WorkflowCapabilityHttpAdapter } from "../../src/external/workflow-capability.js";

describe("WorkflowCapabilityHttpAdapter", () => {
  it("invokes provider-owned capability runs on allowed hosts", async () => {
    const adapter = new WorkflowCapabilityHttpAdapter({
      baseUrl: "https://workflow.test",
      allowedHosts: ["workflow.test"],
      fetcher: async (_url, init) => ({
        status: 200,
        text: async () =>
          JSON.stringify({
            external_run_id: "cap_run_1",
            status: "queued",
            provider_owned: true,
            output: { body: init?.body },
          }),
      }),
    });

    const result = await adapter.invokeCapability({
      capability_key: "workflow.report",
      input: { topic: "Aithru" },
      run_id: "run_1",
    });

    expect(result.external_run_id).toBe("cap_run_1");
    expect(result.provider_owned).toBe(true);
  });

  it("rejects WorkflowSpec-shaped inputs", async () => {
    const adapter = new WorkflowCapabilityHttpAdapter({
      baseUrl: "https://workflow.test",
      allowedHosts: ["workflow.test"],
      fetcher: async () => ({ status: 200, text: async () => "{}" }),
    });

    await expect(
      adapter.invokeCapability({
        capability_key: "workflow.run",
        input: { nodes: [] },
        run_id: "run_1",
      }),
    ).rejects.toThrow("WORKFLOW_SPEC_INPUT_DENIED");
  });
});
