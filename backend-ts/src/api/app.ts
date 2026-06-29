import Fastify from "fastify";
import { registerHealthRoutes } from "./health.js";
import { registerThreadRoutes } from "./threads.js";
import { registerRunRoutes } from "./runs.js";
import { registerApprovalRoutes } from "./approvals.js";
import { createRuntime } from "../application/runtime.js";

export async function createApp() {
  const app = Fastify({ logger: true });

  // Initialize runtime
  await createRuntime();

  // Register routes
  registerHealthRoutes(app);
  registerThreadRoutes(app);
  registerRunRoutes(app);
  registerApprovalRoutes(app);

  return app;
}
