import { describe, expect, it } from "vitest";
import { McpCatalog, McpProviderAdapter } from "@aithru-agent/external";

describe("MCP catalog", () => {
  it("lists enabled server tools without executing them", () => {
    const catalog = new McpCatalog();
    catalog.register({
      id: "srv_1",
      transport: "http",
      enabled: true,
      toolDescriptors: [
        {
          name: "mcp.search",
          description: "Search",
          risk_level: "low",
          requires_approval: false,
          required_scopes: ["mcp:use"],
          input_schema: {},
        },
      ],
    });
    catalog.register({
      id: "srv_2",
      transport: "stdio",
      enabled: false,
      toolDescriptors: [
        {
          name: "mcp.disabled",
          description: "Disabled",
          risk_level: "low",
          requires_approval: false,
          required_scopes: ["mcp:use"],
          input_schema: {},
        },
      ],
    });

    const adapter = new McpProviderAdapter(catalog);
    expect(adapter.listAvailableTools().map((tool) => tool.name)).toEqual([
      "mcp.search",
    ]);
  });
});
