import Fastify from "fastify";
import { createRuntime } from "./runtime.js";
import { registerApprovalRoutes } from "./routes/approvals.js";
import { registerHealthRoutes } from "./routes/health.js";
import { registerCompatRoutes } from "./routes/compat.js";
import { registerRunRoutes } from "./routes/runs.js";
import { registerThreadRoutes } from "./routes/threads.js";

export interface CreateAppOptions {
  dbPath?: string;
}

export async function createApp(options: CreateAppOptions = {}) {
  const app = Fastify({ logger: true });

  await createRuntime(options.dbPath);

  registerHealthRoutes(app);
  registerThreadRoutes(app);
  registerRunRoutes(app);
  registerApprovalRoutes(app);
  registerCompatRoutes(app);

  return app;
}
