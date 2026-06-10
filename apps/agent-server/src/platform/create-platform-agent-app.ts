import express from "express";
import { aithruExpressMiddleware } from "@aithru/subsystem-sdk-node/express";
import type { AithruPlatform } from "@aithru/subsystem-sdk-node";
import type { AgentServerRuntime } from "../runtime/create-agent-server-runtime.js";
import { handleRequest } from "../server/routes.js";
import { createPlatformAgentHttpContext } from "./actor-context.js";

/**
 * Create an Express app for platform subsystem mode.
 *
 * Routes are mounted under /api/agent.
 * Health check is unauthenticated.
 * All other routes require a platform-issued JWT (verified by aithruExpressMiddleware).
 *
 * Important: we do NOT mount express.json() before handleRequest because
 * handleRequest reads the raw request stream via parseJsonBody.
 */
export function createPlatformAgentApp(
  aithru: AithruPlatform,
  rt: AgentServerRuntime,
): express.Application {
  const app = express();

  // Unauthenticated health check
  app.get("/health", (_req, res) => {
    res.json({ ok: true, service: "agent-server", mode: "platform" });
  });

  // Minimal hosted app placeholder
  app.get("/", (_req, res) => {
    res.type("html").send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Aithru Agent</title>
  <style>
    body { font-family: system-ui, sans-serif; padding: 2rem; background: #0f0f0f; color: #e0e0e0; }
    h1 { color: #fff; }
  </style>
</head>
<body>
  <h1>Aithru Agent</h1>
  <p>Platform-hosted AI harness subsystem</p>
  <ul>
    <li><a href="/health" style="color:#6cf">Health</a></li>
  </ul>
</body>
</html>`);
  });

  // Mount authenticated agent API routes under /api/agent
  // aithruExpressMiddleware verifies the JWT and establishes CurrentActor
  app.use("/api/agent", aithruExpressMiddleware(aithru), async (req, res) => {
    const ctx = createPlatformAgentHttpContext(aithru);
    // req.url is rewritten by Express to include /api/agent prefix.
    // handleRequest uses req.url to parse the path, so we need to strip
    // the /api/agent prefix from req.url before passing to handleRequest.
    const originalUrl = req.url;
    req.url = originalUrl.replace(/^\/api\/agent/, "") || "/";
    await handleRequest(req, res, rt, ctx);
  });

  return app;
}
