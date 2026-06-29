import Fastify from "fastify";
import { registerHealthRoutes } from "./health.js";
import { registerThreadRoutes } from "./threads.js";
import { registerRunRoutes } from "./runs.js";
import { createRuntime } from "../application/runtime.js";

export function createApp() {
  const app = Fastify({ logger: true });

  // Initialize runtime
  createRuntime();

  // Register routes
  registerHealthRoutes(app);
  registerThreadRoutes(app);
  registerRunRoutes(app);

  return app;
}
