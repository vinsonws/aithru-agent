import { afterEach, describe, expect, it, vi } from "vitest";
import { McpCatalog, McpProviderAdapter } from "@aithru-agent/external";

afterEach(() => {
  vi.restoreAllMocks();
});

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

  it("executes tools through a registered executor", async () => {
    const catalog = new McpCatalog();
    catalog.register({
      id: "srv_exec",
      transport: "http",
      enabled: true,
      toolDescriptors: [
        {
          name: "mcp.echo",
          description: "Echo",
          risk_level: "low",
          requires_approval: false,
          required_scopes: ["mcp:use"],
          input_schema: {},
        },
      ],
      executeTool: async ({ toolName, input }) => ({ toolName, input }),
    });

    await expect(new McpProviderAdapter(catalog).executeTool("mcp.echo", { q: "hi" })).resolves.toEqual({
      toolName: "mcp.echo",
      input: { q: "hi" },
    });
  });

  it("executes HTTP MCP tools with JSON-RPC tools/call", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ jsonrpc: "2.0", id: "1", result: { found: true } }),
    } as Response);
    const catalog = new McpCatalog();
    catalog.register({
      id: "srv_http",
      transport: "http",
      enabled: true,
      http: { url: "https://mcp.example.test" },
      toolDescriptors: [
        {
          name: "mcp.find",
          description: "Find",
          risk_level: "low",
          requires_approval: false,
          required_scopes: ["mcp:use"],
          input_schema: {},
        },
      ],
    });

    const output = await new McpProviderAdapter(catalog).executeTool("mcp.find", { query: "x" });
    const request = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body));

    expect(output).toEqual({ found: true });
    expect(fetchMock.mock.calls[0][0]).toBe("https://mcp.example.test");
    expect(request).toMatchObject({
      method: "tools/call",
      params: { name: "mcp.find", arguments: { query: "x" } },
    });
  });

  it("executes stdio MCP tools with JSON-RPC tools/call", async () => {
    const catalog = new McpCatalog();
    catalog.register({
      id: "srv_stdio",
      transport: "stdio",
      enabled: true,
      stdio: {
        command: process.execPath,
        args: [
          "--input-type=module",
          "-e",
          [
            "let data = '';",
            "process.stdin.on('data', (chunk) => data += chunk);",
            "process.stdin.on('end', () => {",
            "  const request = JSON.parse(data);",
            "  console.log(JSON.stringify({ jsonrpc: '2.0', id: request.id, result: { name: request.params.name } }));",
            "});",
          ].join("\n"),
        ],
      },
      toolDescriptors: [
        {
          name: "mcp.local",
          description: "Local",
          risk_level: "low",
          requires_approval: false,
          required_scopes: ["mcp:use"],
          input_schema: {},
        },
      ],
    });

    await expect(new McpProviderAdapter(catalog).executeTool("mcp.local", {})).resolves.toEqual({
      name: "mcp.local",
    });
  });
});
