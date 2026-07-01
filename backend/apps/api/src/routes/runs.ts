import type { FastifyInstance } from "fastify";
import { nanoid } from "nanoid";
import { getRuntime } from "../runtime.js";
import type { AgentRun, AgentMessage, AgentStreamEvent } from "@aithru-agent/contracts";
import { CreateRunRequestSchema } from "@aithru-agent/contracts";
import { emitSkillActivated } from "@aithru-agent/harness";
import { EVENT_TYPES } from "@aithru-agent/stream";
import { projectTraceSpans } from "@aithru-agent/trace";
import { buildRunSnapshot } from "@aithru-agent/snapshots";
import { projectCapabilityAudit } from "@aithru-agent/capabilities";
import { shouldFollowRunStream, writeRunStream } from "./run-stream.js";

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function workspaceIdForThread(threadId: string | null): string {
  return threadId ? `ws_thread_${threadId}` : `ws_${nanoid(12)}`;
}

function afterSequence(query: unknown): number {
  const raw = (query as any)?.after_sequence;
  const value = typeof raw === "string" ? Number(raw) : 0;
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function selectedSkillKeys(body: any): string[] {
  const raw = Array.isArray(body.selected_skill_keys) ? body.selected_skill_keys : [];
  const keys: string[] = [];
  for (const value of raw) {
    if (typeof value !== "string") continue;
    const key = value.trim();
    if (!key || keys.includes(key)) continue;
    keys.push(key);
  }
  return keys;
}

export function registerRunRoutes(app: FastifyInstance): void {
  // POST /api/runs
  app.post(
    "/api/runs",
    {
      schema: {
        body: CreateRunRequestSchema,
      },
    },
    async (request, reply) => {
      const body = request.body as any;
      const runtime = getRuntime();
      const threadId = typeof body.thread_id === "string" && body.thread_id.length > 0 ? body.thread_id : null;
      const selectedSkills = [];
      for (const key of selectedSkillKeys(body)) {
        const skill = runtime.skillResolver.resolve(key, body.org_id, body.actor_user_id);
        if (!skill) {
          reply.code(400);
          return { error: `Skill not found: ${key}` };
        }
        selectedSkills.push(skill);
      }
      const run: AgentRun = {
        id: `run_${nanoid(12)}`,
        org_id: body.org_id,
        actor_user_id: body.actor_user_id,
        source: body.source || "chat",
        thread_id: threadId,
        workspace_id: workspaceIdForThread(threadId),
        task_msg: body.task_msg,
        scopes: Array.isArray(body.scopes) && body.scopes.length > 0 ? body.scopes : ["*"],
        harness_options:
          body.harness_options && typeof body.harness_options === "object"
            ? body.harness_options
            : null,
        status: "queued",
        current_approval_id: null,
        started_at: now(),
        completed_at: null,
        claim: null,
        result: null,
        error: null,
      };
      runtime.store.createRun(run);
      if (body.persist_task_msg_message === true && threadId && runtime.store.getThread(threadId)) {
        const message: AgentMessage = {
          id: `msg_${nanoid(12)}`,
          thread_id: threadId,
          role: "user",
          content: body.task_msg,
          run_id: run.id,
          workspace_paths: [],
          created_at: now(),
        };
        runtime.store.createMessage(message);
        runtime.store.updateThread(threadId, { updated_at: now() });
      }

      // Emit run.created
      runtime.eventWriter.write(
        run.id,
        run.thread_id ?? null,
        EVENT_TYPES.RUN_CREATED,
        { run_id: run.id, status: run.status },
      );
      for (const skill of selectedSkills) {
        emitSkillActivated({
          eventWriter: runtime.eventWriter,
          runId: run.id,
          threadId: run.thread_id ?? null,
          key: skill.key,
          name: skill.name,
          source: skill.source,
          version: skill.version,
          trigger: "explicit",
          allowedTools: skill.allowed_tools,
          deniedTools: skill.denied_tools,
        });
      }

      reply.code(201);
      if (body.wait_for_completion === true) {
        return (await runtime.scheduleRunExecution(run, { wait: true })) ?? run;
      }
      void runtime.scheduleRunExecution(run);
      return run;
    },
  );

  // GET /api/runs
  app.get(
    "/api/runs",
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
      void runtime.scheduleRunExecution(run);
      await writeRunStream({
        request,
        reply,
        runtime,
        runId: run_id,
        minSequence: afterSequence(request.query),
        follow: shouldFollowRunStream(request.query),
      });
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

  // POST /api/runs/:run_id/cancel
  app.post(
    "/api/runs/:run_id/cancel",
    async (request, reply) => {
      const { run_id } = request.params as any;
      const runtime = getRuntime();
      const cancelled = runtime.cancelRun(run_id);
      if (!cancelled) {
        reply.code(404);
        return { error: "Run not found" };
      }
      return cancelled;
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
