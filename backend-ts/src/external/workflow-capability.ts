import type { ControlledWebFetch } from "./controlled-web.js";

export interface WorkflowCapabilityRequest {
  capability_key: string;
  input: Record<string, unknown>;
  run_id: string;
}

export interface WorkflowCapabilityResult {
  external_run_id: string;
  status: "queued" | "running" | "completed" | "failed";
  provider_owned: true;
  output?: unknown;
}

export class WorkflowCapabilityHttpAdapter {
  private allowedHosts: Set<string>;

  constructor(
    private config: {
      baseUrl: string;
      allowedHosts: string[];
      fetcher: ControlledWebFetch;
    },
  ) {
    this.allowedHosts = new Set(
      config.allowedHosts.map((host) => host.toLowerCase()),
    );
  }

  async invokeCapability(
    request: WorkflowCapabilityRequest,
  ): Promise<WorkflowCapabilityResult> {
    if (
      "workflow_spec" in request.input ||
      "nodes" in request.input ||
      "edges" in request.input
    ) {
      throw new Error("WORKFLOW_SPEC_INPUT_DENIED");
    }

    const endpoint = new URL("/capabilities/runs", this.config.baseUrl);
    if (!this.allowedHosts.has(endpoint.host.toLowerCase())) {
      throw new Error(`WORKFLOW_HOST_DENIED: ${endpoint.host}`);
    }

    const response = await this.config.fetcher(endpoint.toString(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    });
    const body = JSON.parse(await response.text()) as WorkflowCapabilityResult;
    return { ...body, provider_owned: true };
  }
}
