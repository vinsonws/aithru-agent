import Fastify from "fastify";
import { createRuntime } from "./runtime.js";
import { registerApprovalRoutes } from "./routes/approvals.js";
import { registerHealthRoutes } from "./routes/health.js";
import { registerCompatRoutes } from "./routes/compat.js";
import { registerModelConfigRoutes } from "./routes/model-config.js";
import { registerRunRoutes } from "./routes/runs.js";
import { registerThreadRoutes } from "./routes/threads.js";
import {
  createAgentPlatform,
  registerPlatformAuth,
  shouldEnablePlatformAuth,
} from "./platform-auth.js";

export interface CreateAppOptions {
  dbPath?: string;
}

export async function createApp(options: CreateAppOptions = {}) {
  const app = Fastify({ logger: true });

  await createRuntime(options.dbPath);
  if (shouldEnablePlatformAuth()) {
    const platform = createAgentPlatform();
    await platform.start();
    registerPlatformAuth(app, platform);
    app.addHook("onClose", async () => {
      await platform.stop();
    });
  }

  registerHealthRoutes(app);
  registerThreadRoutes(app);
  registerRunRoutes(app);
  registerApprovalRoutes(app);
  registerCompatRoutes(app);
  registerModelConfigRoutes(app);

  return app;
}
