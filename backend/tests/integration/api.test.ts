import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { createApp } from "@aithru-agent/api";
import type { FastifyInstance } from "fastify";

let app: FastifyInstance;

beforeAll(async () => {
  app = await createApp();
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

describe("Health API", () => {
  it("GET /api/health returns ok", async () => {
    const res = await app.inject({ method: "GET", url: "/api/health" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.status).toBe("ok");
  });
});

describe("Threads API", () => {
  let threadId: string;

  it("POST /api/threads creates a thread", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/threads",
      payload: {
        org_id: "org_1",
        owner_user_id: "user_1",
        title: "Test Thread",
      },
    });
    expect(res.statusCode).toBe(201);
    const body = JSON.parse(res.body);
    expect(body.id).toMatch(/^thread_/);
    expect(body.status).toBe("active");
    threadId = body.id;
  });

  it("GET /api/threads lists threads", async () => {
    const res = await app.inject({
      method: "GET",
      url: "/api/threads?org_id=org_1",
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBeGreaterThanOrEqual(1);
  });

  it("PATCH /api/threads/:id updates a thread", async () => {
    const res = await app.inject({
      method: "PATCH",
      url: `/api/threads/${threadId}`,
      payload: { title: "Updated Title" },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.title).toBe("Updated Title");
  });

  it("POST /api/threads/:id/messages creates a message", async () => {
    const res = await app.inject({
      method: "POST",
      url: `/api/threads/${threadId}/messages`,
      payload: { role: "user", content: "Hello" },
    });
    expect(res.statusCode).toBe(201);
    const body = JSON.parse(res.body);
    expect(body.role).toBe("user");
    expect(body.content).toBe("Hello");
  });

  it("GET /api/threads/:id/messages lists messages", async () => {
    const res = await app.inject({
      method: "GET",
      url: `/api/threads/${threadId}/messages`,
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.length).toBeGreaterThanOrEqual(1);
  });
});

describe("Runs API", () => {
  let runId: string;

  it("POST /api/runs creates a run", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "org_1",
        actor_user_id: "user_1",
        source: "chat",
        task_msg: "Do something",
      },
    });
    expect(res.statusCode).toBe(201);
    const body = JSON.parse(res.body);
    expect(body.id).toMatch(/^run_/);
    expect(body.status).toBe("queued");
    expect(body.workspace_id).toMatch(/^ws_/);
    runId = body.id;
  });

  it("GET /api/runs lists runs", async () => {
    const res = await app.inject({ method: "GET", url: "/api/runs" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body)).toBe(true);
  });

  it("GET /api/runs/:id gets a run", async () => {
    const res = await app.inject({ method: "GET", url: `/api/runs/${runId}` });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.id).toBe(runId);
  });

  it("GET /api/runs/:id/stream returns SSE", async () => {
    const res = await app.inject({
      method: "GET",
      url: `/api/runs/${runId}/stream`,
    });
    expect(res.statusCode).toBe(200);
    expect(res.headers["content-type"]).toContain("text/event-stream");
  });

  it("GET /api/runs/:id/events returns event list", async () => {
    const res = await app.inject({
      method: "GET",
      url: `/api/runs/${runId}/events`,
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body)).toBe(true);
    // run.created should be there from POST
    expect(body.some((e: any) => e.type === "run.created")).toBe(true);
  });

  it("POST /api/runs/:id/cancel cancels a run", async () => {
    const res = await app.inject({
      method: "POST",
      url: `/api/runs/${runId}/cancel`,
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.cancelled).toBe(true);

    // Verify run status
    const getRes = await app.inject({
      method: "GET",
      url: `/api/runs/${runId}`,
    });
    const run = JSON.parse(getRes.body);
    expect(run.status).toBe("cancelled");
  });
});
