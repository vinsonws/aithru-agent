import type { AgentToolDescriptor } from "../capabilities/descriptors.js";

export type McpTransportKind = "http" | "stdio";

export interface McpServerConfig {
  id: string;
  transport: McpTransportKind;
  enabled: boolean;
  toolDescriptors: AgentToolDescriptor[];
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
}

export class McpProviderAdapter {
  constructor(private catalog: McpCatalog) {}

  listAvailableTools(): AgentToolDescriptor[] {
    return this.catalog.listTools();
  }
}
