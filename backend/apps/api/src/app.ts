import Fastify from "fastify";
import { createRuntime } from "./runtime.js";
import { registerApprovalRoutes } from "./routes/approvals.js";
import { registerHealthRoutes } from "./routes/health.js";
import { registerRunRoutes } from "./routes/runs.js";
import { registerThreadRoutes } from "./routes/threads.js";

export async function createApp() {
  const app = Fastify({ logger: true });

  await createRuntime();

  registerHealthRoutes(app);
  registerThreadRoutes(app);
  registerRunRoutes(app);
  registerApprovalRoutes(app);

  return app;
}
