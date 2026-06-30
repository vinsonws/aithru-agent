import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { createApp, getRuntime } from "@aithru-agent/api";
import type { AgentRun } from "@aithru-agent/contracts";
import { EVENT_TYPES } from "@aithru-agent/stream";
import type { FastifyInstance } from "fastify";

let app: FastifyInstance;

beforeAll(async () => {
  app = await createApp();
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

function testNow(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

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

  it("uses one workspace id for runs in the same thread", async () => {
    const thread = await app.inject({
      method: "POST",
      url: "/api/threads",
      payload: {
        org_id: "org_1",
        owner_user_id: "user_1",
        title: "Workspace sharing",
      },
    });
    const threadId = JSON.parse(thread.body).id;
    const first = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "org_1",
        actor_user_id: "user_1",
        source: "chat",
        thread_id: threadId,
        task_msg: "First threaded run",
      },
    });
    const second = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "org_1",
        actor_user_id: "user_1",
        source: "chat",
        thread_id: threadId,
        task_msg: "Second threaded run",
      },
    });
    expect(first.statusCode).toBe(201);
    expect(second.statusCode).toBe(201);
    expect(JSON.parse(first.body).workspace_id).toBe(JSON.parse(second.body).workspace_id);
  });

  it("generates a title for untitled completed model threads", async () => {
    const thread = await app.inject({
      method: "POST",
      url: "/api/threads",
      payload: {
        org_id: "org_1",
        owner_user_id: "user_1",
      },
    });
    const threadId = JSON.parse(thread.body).id;
    const run = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "org_1",
        actor_user_id: "user_1",
        source: "chat",
        thread_id: threadId,
        task_msg: "Plan the launch checklist",
        harness_options: { model_profile_key: "default" },
        persist_task_msg_message: true,
        wait_for_completion: true,
      },
    });

    expect(run.statusCode).toBe(201);
    expect(JSON.parse(run.body).status).toBe("completed");
    expect(getRuntime().store.getThread(threadId)?.title).toBe("Generated Thread Title");
    const events = getRuntime().store.listEvents(JSON.parse(run.body).id);
    expect(events.findIndex((event) => event.type === "thread.title.generated")).toBeLessThan(
      events.findIndex((event) => event.type === "run.completed"),
    );
  });

  it("does not overwrite existing thread titles after model runs", async () => {
    const thread = await app.inject({
      method: "POST",
      url: "/api/threads",
      payload: {
        org_id: "org_1",
        owner_user_id: "user_1",
        title: "Manual title",
      },
    });
    const threadId = JSON.parse(thread.body).id;
    await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "org_1",
        actor_user_id: "user_1",
        source: "chat",
        thread_id: threadId,
        task_msg: "Replace the title",
        harness_options: { model_profile_key: "default" },
        persist_task_msg_message: true,
        wait_for_completion: true,
      },
    });

    expect(getRuntime().store.getThread(threadId)?.title).toBe("Manual title");
  });

  it("POST /api/runs activates selected skills before model execution", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "org_1",
        actor_user_id: "user_1",
        source: "chat",
        task_msg: "Surprise me",
        selected_skill_keys: ["surprise-me", "surprise-me"],
        harness_options: { model_profile_key: "default" },
        wait_for_completion: true,
      },
    });

    expect(res.statusCode).toBe(201);
    const run = JSON.parse(res.body);
    const events = getRuntime().store.listEvents(run.id);
    expect(
      events
        .filter((event) => event.type === "skill.activated")
        .map((event) => (event.payload as any).key),
    ).toEqual(["surprise-me"]);
    expect(events.find((event) => event.type === "skill.activated")?.sequence).toBeLessThan(
      events.find((event) => event.type === "run.started")!.sequence,
    );
  });

  it("POST /api/runs rejects unknown selected skills", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "org_1",
        actor_user_id: "user_1",
        task_msg: "Use a missing skill",
        selected_skill_keys: ["missing-skill"],
      },
    });

    expect(res.statusCode).toBe(400);
    expect(JSON.parse(res.body)).toEqual({ error: "Skill not found: missing-skill" });
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

  it("GET /api/runs/:id/stream?follow=true waits for new run events", async () => {
    const runtime = getRuntime();
    const run: AgentRun = {
      id: "run_live_stream_test",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "chat",
      thread_id: null,
      workspace_id: "ws_live_stream_test",
      task_msg: "stream later",
      scopes: ["*"],
      harness_options: null,
      status: "running",
      current_approval_id: null,
      started_at: testNow(),
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    };
    runtime.store.createRun(run);
    runtime.eventWriter.write(run.id, null, EVENT_TYPES.RUN_STARTED, {
      run_id: run.id,
      status: "running",
    });

    const stream = app.inject({
      method: "GET",
      url: `/api/runs/${run.id}/stream?follow=true&after_sequence=1`,
    });

    await wait(30);
    runtime.eventWriter.write(run.id, null, EVENT_TYPES.MESSAGE_DELTA, {
      message_id: "msg_live_stream_test",
      delta: "live token",
    });
    runtime.store.updateRun(run.id, {
      status: "completed",
      completed_at: testNow(),
    });
    runtime.eventWriter.write(run.id, null, EVENT_TYPES.RUN_COMPLETED, {
      run_id: run.id,
      status: "completed",
    });

    const res = await stream;
    expect(res.statusCode).toBe(200);
    expect(res.body).toContain("event: message.delta");
    expect(res.body).toContain("live token");
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
    expect(body.id).toBe(runId);
    expect(body.status).toBe("cancelled");

    // Verify run status
    const getRes = await app.inject({
      method: "GET",
      url: `/api/runs/${runId}`,
    });
    const run = JSON.parse(getRes.body);
    expect(run.status).toBe("cancelled");
  });
});
