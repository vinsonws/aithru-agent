import type { FastifyInstance } from "fastify";
import { HealthResponseSchema } from "@aithru-agent/contracts";

export function registerHealthRoutes(app: FastifyInstance): void {
  app.get(
    "/api/health",
    {
      schema: {
        response: {
          200: HealthResponseSchema,
        },
      },
    },
    async (_request, _reply) => {
      return { status: "ok", version: "0.1.0" };
    },
  );
}
