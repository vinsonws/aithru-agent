import type { FastifyInstance } from "fastify";
import { nanoid } from "nanoid";
import { getRuntime } from "../runtime.js";
import type { AgentThread, AgentMessage } from "@aithru-agent/contracts";
import {
  CreateThreadRequestSchema,
  UpdateThreadRequestSchema,
  CreateMessageRequestSchema,
  AgentThreadSchema,
  AgentMessageSchema,
} from "@aithru-agent/contracts";

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

export function registerThreadRoutes(app: FastifyInstance): void {
  // POST /api/threads
  app.post(
    "/api/threads",
    {
      schema: {
        body: CreateThreadRequestSchema,
        response: {
          201: AgentThreadSchema,
        },
      },
    },
    async (request, reply) => {
      const body = request.body as any;
      const runtime = getRuntime();
      const thread: AgentThread = {
        id: `thread_${nanoid(12)}`,
        org_id: body.org_id,
        owner_user_id: body.owner_user_id,
        title: body.title || null,
        status: "active",
        created_at: now(),
        updated_at: now(),
      };
      runtime.store.createThread(thread);
      reply.code(201);
      return thread;
    },
  );

  // GET /api/threads
  app.get(
    "/api/threads",
    {
      schema: {
        querystring: {
          type: "object",
          properties: {
            org_id: { type: "string" },
          },
        },
        response: {
          200: {
            type: "array",
            items: AgentThreadSchema,
          },
        },
      },
    },
    async (request) => {
      const { org_id } = (request.query as any) || {};
      const runtime = getRuntime();
      return runtime.store.listThreads(org_id);
    },
  );

  // PATCH /api/threads/:thread_id
  app.patch(
    "/api/threads/:thread_id",
    {
      schema: {
        body: UpdateThreadRequestSchema,
        response: {
          200: AgentThreadSchema,
          404: {
            type: "object",
            properties: { error: { type: "string" } },
          },
        },
      },
    },
    async (request, reply) => {
      const { thread_id } = request.params as any;
      const body = request.body as any;
      const runtime = getRuntime();
      const existing = runtime.store.getThread(thread_id);
      if (!existing) {
        reply.code(404);
        return { error: "Thread not found" };
      }
      const updated = runtime.store.updateThread(thread_id, {
        ...(body.title !== undefined ? { title: body.title } : {}),
        ...(body.status !== undefined ? { status: body.status } : {}),
        updated_at: now(),
      });
      return updated;
    },
  );

  // POST /api/threads/:thread_id/messages
  app.post(
    "/api/threads/:thread_id/messages",
    {
      schema: {
        body: CreateMessageRequestSchema,
        response: {
          201: AgentMessageSchema,
          404: {
            type: "object",
            properties: { error: { type: "string" } },
          },
        },
      },
    },
    async (request, reply) => {
      const { thread_id } = request.params as any;
      const body = request.body as any;
      const runtime = getRuntime();
      const thread = runtime.store.getThread(thread_id);
      if (!thread) {
        reply.code(404);
        return { error: "Thread not found" };
      }
      const message: AgentMessage = {
        id: `msg_${nanoid(12)}`,
        thread_id,
        role: body.role,
        content: body.content,
        run_id: body.run_id || null,
        workspace_paths: [],
        created_at: now(),
      };
      runtime.store.createMessage(message);
      thread.updated_at = now();
      runtime.store.updateThread(thread_id, { updated_at: now() });
      reply.code(201);
      return message;
    },
  );

  // GET /api/threads/:thread_id/messages
  app.get(
    "/api/threads/:thread_id/messages",
    {
      schema: {
        response: {
          200: {
            type: "array",
            items: AgentMessageSchema,
          },
          404: {
            type: "object",
            properties: { error: { type: "string" } },
          },
        },
      },
    },
    async (request, reply) => {
      const { thread_id } = request.params as any;
      const runtime = getRuntime();
      const thread = runtime.store.getThread(thread_id);
      if (!thread) {
        reply.code(404);
        return { error: "Thread not found" };
      }
      return runtime.store.listMessages(thread_id);
    },
  );
}
