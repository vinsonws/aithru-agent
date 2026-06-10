import { createServer, type Server } from "node:http";
import type { AgentServerRuntime } from "../runtime/create-agent-server-runtime.js";
import { handleRequest } from "./routes.js";

/**
 * Create an HTTP server using the provided runtime.
 *
 * Uses Node's built-in http module — no external framework dependency.
 */
export function createAgentHttpServer(rt: AgentServerRuntime): Server {
  return createServer((req, res) => {
    handleRequest(req, res, rt);
  });
}

export function startAgentServer(rt: AgentServerRuntime, host: string, port: number): Server {
  const server = createAgentHttpServer(rt);

  server.listen(port, host, () => {
    console.log(`Aithru Agent Server listening on http://${host}:${port}`);
  });

  return server;
}
