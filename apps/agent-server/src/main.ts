import { createAgentServerRuntime } from "./runtime/create-agent-server-runtime.js";
import { startAgentServer } from "./server/create-agent-http-server.js";

const HOST = process.env.AITHRU_AGENT_SERVER_HOST ?? "127.0.0.1";
const PORT = parseInt(process.env.AITHRU_AGENT_SERVER_PORT ?? "4317", 10);

const rt = createAgentServerRuntime();
const server = startAgentServer(rt, HOST, PORT);

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\nShutting down...");
  server.close(() => process.exit(0));
});

process.on("SIGTERM", () => {
  server.close(() => process.exit(0));
});
