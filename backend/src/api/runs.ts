import type { FastifyInstance } from "fastify";
import { nanoid } from "nanoid";
import { getRuntime } from "../application/runtime.js";
import type { AgentRun, AgentStreamEvent } from "@aithru-agent/contracts";
import {
  CreateRunRequestSchema,
  AgentRunSchema,
} from "@aithru-agent/contracts";
import { formatSseEvent, formatSseComment, EVENT_TYPES } from "@aithru-agent/stream";
import { projectTraceSpans } from "@aithru-agent/trace";
import { buildRunSnapshot } from "@aithru-agent/snapshots";
import { projectCapabilityAudit } from "@aithru-agent/capabilities";

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

export function registerRunRoutes(app: FastifyInstance): void {
  // POST /api/runs
  app.post(
    "/api/runs",
    {
      schema: {
        body: CreateRunRequestSchema,
        response: {
          201: AgentRunSchema,
        },
      },
    },
    async (request, reply) => {
      const body = request.body as any;
      const runtime = getRuntime();
      const run: AgentRun = {
        id: `run_${nanoid(12)}`,
        org_id: body.org_id,
        actor_user_id: body.actor_user_id,
        source: body.source,
        thread_id: body.thread_id || null,
        skill_id: body.skill_id || null,
        workspace_id: `ws_${nanoid(12)}`,
        task_msg: body.task_msg,
        scopes: body.scopes || ["*"],
        harness_options: null,
        status: "queued",
        current_approval_id: null,
        started_at: now(),
        completed_at: null,
        claim: null,
        result: null,
        error: null,
      };
      runtime.store.createRun(run);

      // Emit run.created
      runtime.eventWriter.write(
        run.id,
        run.thread_id ?? null,
        EVENT_TYPES.RUN_CREATED,
        { run_id: run.id, status: run.status },
      );

      reply.code(201);
      return run;
    },
  );

  // GET /api/runs
  app.get(
    "/api/runs",
    {
      schema: {
        response: {
          200: {
            type: "array",
            items: AgentRunSchema,
          },
        },
      },
    },
    async (request) => {
      const { org_id, thread_id } = (request.query as any) || {};
      const runtime = getRuntime();
      return runtime.store.listRuns({ org_id, thread_id });
    },
  );

  // GET /api/runs/:run_id
  app.get(
    "/api/runs/:run_id",
    {
      schema: {
        response: {
          200: AgentRunSchema,
          404: {
            type: "object",
            properties: { error: { type: "string" } },
          },
        },
      },
    },
    async (request, reply) => {
      const { run_id } = request.params as any;
      const runtime = getRuntime();
      const run = runtime.store.getRun(run_id);
      if (!run) {
        reply.code(404);
        return { error: "Run not found" };
      }
      return run;
    },
  );

  // GET /api/runs/:run_id/stream (SSE)
  app.get(
    "/api/runs/:run_id/stream",
    async (request, reply) => {
      const { run_id } = request.params as any;
      const runtime = getRuntime();
      const run = runtime.store.getRun(run_id);
      if (!run) {
        reply.code(404);
        return { error: "Run not found" };
      }

      reply.raw.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      });

      // Send already-persisted events (replay)
      const existingEvents = runtime.store.listEvents(run_id);
      for (const event of existingEvents) {
        reply.raw.write(formatSseEvent(event));
      }

      // Send a keepalive comment
      reply.raw.write(formatSseComment("stream ready"));

      // In P0, we don't do live following — just replay then close
      // P1+ will add live event following
      reply.raw.end();
    },
  );

  // GET /api/runs/:run_id/events
  app.get(
    "/api/runs/:run_id/events",
    async (request, reply) => {
      const { run_id } = request.params as any;
      const runtime = getRuntime();
      const run = runtime.store.getRun(run_id);
      if (!run) {
        reply.code(404);
        return { error: "Run not found" };
      }
      return runtime.store.listEvents(run_id);
    },
  );

  // POST /api/runs/:run_id/cancel (stub for P0)
  app.post(
    "/api/runs/:run_id/cancel",
    async (request, reply) => {
      const { run_id } = request.params as any;
      const runtime = getRuntime();
      const run = runtime.store.getRun(run_id);
      if (!run) {
        reply.code(404);
        return { error: "Run not found" };
      }
      runtime.store.updateRun(run_id, {
        status: "cancelled",
        completed_at: now(),
      });
      runtime.eventWriter.write(
        run_id,
        run.thread_id ?? null,
        EVENT_TYPES.RUN_CANCELLED,
        { run_id },
      );
      return { cancelled: true, run_id };
    },
  );

  // GET /api/runs/:run_id/trace
  app.get("/api/runs/:run_id/trace", async (request, reply) => {
    const { run_id } = request.params as any;
    const runtime = getRuntime();
    const run = runtime.store.getRun(run_id);
    if (!run) {
      reply.code(404);
      return { error: "Run not found" };
    }
    const events = runtime.store.listEvents(run_id);
    const spans = projectTraceSpans(events);
    return spans;
  });

  // GET /api/runs/:run_id/snapshot
  app.get("/api/runs/:run_id/snapshot", async (request, reply) => {
    const { run_id } = request.params as any;
    const runtime = getRuntime();
    const snapshot = buildRunSnapshot(runtime.store, run_id);
    if (!snapshot) { reply.code(404); return { error: "Run not found" }; }
    return snapshot;
  });

  // GET /api/runs/:run_id/capability-audit
  app.get("/api/runs/:run_id/capability-audit", async (request, reply) => {
    const { run_id } = request.params as any;
    const runtime = getRuntime();
    const run = runtime.store.getRun(run_id);
    if (!run) {
      reply.code(404);
      return { error: "Run not found" };
    }
    return projectCapabilityAudit(runtime.store.listEvents(run_id));
  });
}
