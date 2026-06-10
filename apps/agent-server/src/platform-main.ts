import { loadPlatformConfig } from "./platform/config.js";
import { createAgentAithruPlatform } from "./platform/create-aithru-platform.js";
import { createAgentServerRuntime } from "./runtime/create-agent-server-runtime.js";
import { createPlatformAgentApp } from "./platform/create-platform-agent-app.js";
import type { Server } from "node:http";

const config = loadPlatformConfig();

console.log(`[agent-server] Starting platform subsystem mode...`);
console.log(`[agent-server]   port:     ${config.port}`);
console.log(`[agent-server]   platform: ${config.platformUrl}`);
console.log(`[agent-server]   app:      ${config.appKey}`);
console.log(`[agent-server]   service:  ${config.serviceName}`);

const aithru = createAgentAithruPlatform(config);
const rt = createAgentServerRuntime();
const app = createPlatformAgentApp(aithru, rt);

// Start SDK lifecycle (manifest registration, heartbeat)
await aithru.start();

const server: Server = app.listen(config.port, () => {
  console.log(`[agent-server] Platform mode listening on http://127.0.0.1:${config.port}`);
  console.log(`[agent-server]   API base: /api/agent`);
  console.log(`[agent-server]   Health:   /health`);
});

async function shutdown() {
  console.log("\n[agent-server] Shutting down...");
  await aithru.stop();
  await new Promise<void>((resolve) => server.close(() => resolve()));
  console.log("[agent-server] Shutdown complete");
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
