import type { AgentToolDescriptor } from "@aithru-agent/capabilities";
import { spawn } from "node:child_process";

export type McpTransportKind = "http" | "stdio";

export type McpToolExecutor = (args: {
  server: McpServerConfig;
  toolName: string;
  input: Record<string, unknown>;
}) => Promise<unknown>;

export interface McpServerConfig {
  id: string;
  transport: McpTransportKind;
  enabled: boolean;
  toolDescriptors: AgentToolDescriptor[];
  executeTool?: McpToolExecutor;
  http?: {
    url: string;
    headers?: Record<string, string>;
  };
  stdio?: {
    command: string;
    args?: string[];
    timeoutMs?: number;
  };
}

export class McpCatalog {
  private servers = new Map<string, McpServerConfig>();

  register(server: McpServerConfig): void {
    this.servers.set(server.id, server);
  }

  listTools(): AgentToolDescriptor[] {
    return [...this.servers.values()]
      .filter((server) => server.enabled)
      .flatMap((server) => server.toolDescriptors);
  }

  getServer(id: string): McpServerConfig | undefined {
    return this.servers.get(id);
  }

  findServerForTool(toolName: string): McpServerConfig | undefined {
    return [...this.servers.values()].find((server) =>
      server.enabled && server.toolDescriptors.some((tool) => tool.name === toolName),
    );
  }
}

export class McpProviderAdapter {
  constructor(private catalog: McpCatalog) {}

  listAvailableTools(): AgentToolDescriptor[] {
    return this.catalog.listTools();
  }

  async executeTool(toolName: string, input: Record<string, unknown>): Promise<unknown> {
    const server = this.catalog.findServerForTool(toolName);
    if (!server) throw new Error(`MCP_TOOL_NOT_FOUND: ${toolName}`);
    if (server.executeTool) return await server.executeTool({ server, toolName, input });
    if (server.transport === "http" && server.http) return await executeHttpTool(server, toolName, input);
    if (server.transport === "stdio" && server.stdio) return await executeStdioTool(server, toolName, input);
    throw new Error(`MCP_EXECUTOR_NOT_CONFIGURED: ${server.id}`);
  }
}

async function executeHttpTool(
  server: McpServerConfig,
  toolName: string,
  input: Record<string, unknown>,
): Promise<unknown> {
  if (!server.http) throw new Error(`MCP_HTTP_NOT_CONFIGURED: ${server.id}`);
  const response = await fetch(server.http.url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(server.http.headers ?? {}),
    },
    body: JSON.stringify(jsonRpcRequest(toolName, input)),
  });
  const payload = await response.json() as Record<string, unknown>;
  if (!response.ok) throw new Error(`MCP_HTTP_ERROR: ${response.status}`);
  if (payload.error) throw new Error(`MCP_TOOL_ERROR: ${JSON.stringify(payload.error)}`);
  return payload.result ?? payload;
}

function executeStdioTool(
  server: McpServerConfig,
  toolName: string,
  input: Record<string, unknown>,
): Promise<unknown> {
  if (!server.stdio) throw new Error(`MCP_STDIO_NOT_CONFIGURED: ${server.id}`);
  const timeoutMs = Math.min(Math.max(server.stdio.timeoutMs ?? 30_000, 1), 120_000);
  const child = spawn(server.stdio.command, server.stdio.args ?? [], {
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });
  const request = `${JSON.stringify(jsonRpcRequest(toolName, input))}\n`;
  child.stdin.end(request, "utf8");

  return new Promise((resolve, reject) => {
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error(`MCP_STDIO_TIMEOUT: ${server.id}`));
    }, timeoutMs);

    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
    child.once("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(`MCP_STDIO_ERROR: ${Buffer.concat(stderr).toString("utf8").trim() || code}`));
        return;
      }
      try {
        const payload = JSON.parse(Buffer.concat(stdout).toString("utf8").trim()) as Record<string, unknown>;
        if (payload.error) reject(new Error(`MCP_TOOL_ERROR: ${JSON.stringify(payload.error)}`));
        else resolve(payload.result ?? payload);
      } catch (error) {
        reject(error);
      }
    });
  });
}

function jsonRpcRequest(toolName: string, input: Record<string, unknown>) {
  return {
    jsonrpc: "2.0",
    id: `mcp_${Date.now().toString(36)}`,
    method: "tools/call",
    params: { name: toolName, arguments: input },
  };
}
