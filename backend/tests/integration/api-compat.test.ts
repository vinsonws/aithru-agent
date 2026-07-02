import { readFileSync } from "node:fs";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { resolve } from "node:path";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { createApp, getRuntime, resetRuntimeForTests } from "@aithru-agent/api";
import type { AgentRun } from "@aithru-agent/contracts";
import { createToolCallRecord } from "@aithru-agent/harness";
import { EVENT_TYPES } from "@aithru-agent/stream";
import type { FastifyInstance } from "fastify";

type OpenApiDocument = {
  paths: Record<string, Record<string, unknown>>;
  components?: {
    schemas?: Record<
      string,
      {
        properties?: Record<string, unknown>;
      }
    >;
  };
};

const removedRunSkillField = ["skill", "id"].join("_");

const HTTP_METHODS = new Set([
  "delete",
  "get",
  "patch",
  "post",
  "put",
]);

function openApiOperations(): Array<{ method: string; url: string }> {
  const document = JSON.parse(
    readFileSync(resolve("../frontend/openapi.json"), "utf8"),
  ) as OpenApiDocument;
  const operations: Array<{ method: string; url: string }> = [];
  for (const [path, methods] of Object.entries(document.paths)) {
    for (const method of Object.keys(methods)) {
      if (!HTTP_METHODS.has(method)) continue;
      if (path.startsWith("/api/artifacts")) continue;
      if (path.endsWith("/export/artifact")) continue;
      operations.push({
        method: method.toUpperCase(),
        url: path.replace(/\{([^}]+)\}/g, ":$1"),
      });
    }
  }
  return operations.sort((a, b) =>
    `${a.method} ${a.url}`.localeCompare(`${b.method} ${b.url}`),
  );
}

function openApiDocument(): OpenApiDocument {
  return JSON.parse(
    readFileSync(resolve("../frontend/openapi.json"), "utf8"),
  ) as OpenApiDocument;
}

function runCreatedEventCount(): number {
  const runtime = getRuntime();
  return runtime.store
    .listRuns({})
    .reduce(
      (count, run) =>
        count +
        runtime.store.listEvents(run.id).filter((event) => event.type === "run.created").length,
      0,
    );
}

describe("legacy OpenAPI compatibility", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    resetRuntimeForTests();
    app = await createApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
    resetRuntimeForTests();
  });

  it("registers every operation advertised to the frontend", () => {
    const missing = openApiOperations()
      .filter(({ method, url }) => !app.hasRoute({ method, url }))
      .map(({ method, url }) => `${method} ${url}`);

    expect(missing).toEqual([]);
  });

  it("does not advertise unbacked active skill arrays on run read models", () => {
    const document = openApiDocument();
    const schemaNames = [
      "AgentRun",
      "ResolveExternalRunResponse",
      "RunDetailResponse",
      "RunListItem",
      "RunTreeNode",
    ];

    for (const name of schemaNames) {
      expect(
        document.components?.schemas?.[name]?.properties &&
          "active_skill_keys" in document.components.schemas[name].properties!,
      ).toBe(false);
    }
  });

  it("accepts the frontend CreateRunRequest shape", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        task_msg: "frontend shape",
        org_id: "org_1",
        actor_user_id: "user_1",
        scopes: ["workspace:read"],
        selected_skill_keys: null,
        wait_for_completion: false,
        persist_task_msg_message: true,
      },
    });

    expect(res.statusCode).toBe(201);
    const run = JSON.parse(res.body);
    expect(run.source).toBe("chat");
    expect(removedRunSkillField in run).toBe(false);
  });

  async function waitForRunEvents(runId: string, type: string) {
    for (let i = 0; i < 20; i += 1) {
      const res = await app.inject({
        method: "GET",
        url: `/api/runs/${runId}/events`,
      });
      const events = JSON.parse(res.body);
      if (events.some((event: any) => event.type === type)) return events;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    throw new Error(`Timed out waiting for ${type}`);
  }

  it("executes frontend chat runs that select a model profile", async () => {
    const profile = await app.inject({
      method: "POST",
      url: "/api/model-profiles",
      payload: {
        key: "test-chat",
        name: "Test Chat",
        provider: "test",
        model: "test",
        enabled: true,
      },
    });
    expect(profile.statusCode).toBe(201);

    const created = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        task_msg: "say hi",
        org_id: "org_1",
        actor_user_id: "user_1",
        scopes: ["agent.workspace.read"],
        selected_skill_keys: null,
        harness_options: { model_profile_key: "test-chat" },
        wait_for_completion: false,
        persist_task_msg_message: true,
      },
    });

    expect(created.statusCode).toBe(201);
    const run = JSON.parse(created.body);
    expect(run.status).toBe("queued");

    const events = await waitForRunEvents(run.id, "run.completed");
    expect(events.map((event: any) => event.type)).toEqual(
      expect.arrayContaining(["message.delta", "message.completed", "run.completed"]),
    );
    const messageCompleted = events.find((event: any) => event.type === "message.completed");
    expect(messageCompleted.payload.content.length).toBeGreaterThan(0);

    const filtered = await app.inject({
      method: "GET",
      url: `/api/runs/${run.id}/stream?follow=true&after_sequence=1`,
    });
    expect(filtered.statusCode).toBe(200);
    expect(filtered.body).not.toContain('"sequence":1');
  });

  it("streams events from create-run stream POST endpoints", async () => {
    const root = await app.inject({
      method: "POST",
      url: "/api/runs/stream",
      payload: {
        task_msg: "stream root",
        org_id: "org_1",
        actor_user_id: "user_1",
        scopes: ["agent.workspace.read"],
        harness_options: { model_profile_key: "default" },
      },
    });

    expect(root.statusCode).toBe(200);
    expect(root.headers["content-type"]).toContain("text/event-stream");
    expect(root.body).toContain("event: message.delta");
    expect(root.body).toContain("event: run.completed");

    getRuntime().store.createThread({
      id: "thread_create_stream",
      org_id: "org_1",
      owner_user_id: "user_1",
      title: "Stream",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    const threaded = await app.inject({
      method: "POST",
      url: "/api/threads/thread_create_stream/runs/stream",
      payload: {
        task_msg: "stream thread",
        org_id: "org_1",
        actor_user_id: "user_1",
        scopes: ["agent.workspace.read"],
        harness_options: { model_profile_key: "default" },
        persist_task_msg_message: true,
      },
    });

    expect(threaded.statusCode).toBe(200);
    expect(threaded.headers["content-type"]).toContain("text/event-stream");
    expect(threaded.body).toContain("event: message.delta");
    expect(threaded.body).toContain("event: run.completed");

    for (const run of getRuntime().store.listRuns({ thread_id: "thread_create_stream" })) {
      getRuntime().store.updateRun(run.id, {
        started_at: "2025-01-01T00:00:00Z",
        completed_at: "2025-01-01T00:00:01Z",
      });
    }
    getRuntime().store.updateThread("thread_create_stream", {
      updated_at: "2025-01-01T00:00:00Z",
    });
  });

  it("activates selected skills on compatibility create-run endpoints", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/runs/wait",
      payload: {
        task_msg: "Surprise me",
        org_id: "org_1",
        actor_user_id: "user_1",
        selected_skill_keys: ["surprise-me", "surprise-me"],
        harness_options: { model_profile_key: "default" },
      },
    });

    expect(res.statusCode).toBe(200);
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

  it("activates selected skills on threaded compatibility create-run endpoints", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/threads/thread_selected_skill_create/runs",
      payload: {
        task_msg: "Surprise me",
        org_id: "org_1",
        actor_user_id: "user_1",
        selected_skill_keys: ["surprise-me", "surprise-me"],
        harness_options: { model_profile_key: "default" },
        wait_for_completion: true,
      },
    });

    expect(res.statusCode).toBe(200);
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

  it("rejects unknown selected skills on compatibility create-run endpoints", async () => {
    const beforeRuns = getRuntime().store.listRuns({}).length;
    const beforeRunCreatedEvents = runCreatedEventCount();
    const res = await app.inject({
      method: "POST",
      url: "/api/runs/wait",
      payload: {
        task_msg: "Use a missing skill",
        org_id: "org_1",
        actor_user_id: "user_1",
        selected_skill_keys: ["missing-skill"],
      },
    });

    expect(res.statusCode).toBe(400);
    expect(JSON.parse(res.body)).toEqual({ error: "Skill not found: missing-skill" });
    expect(getRuntime().store.listRuns({}).length).toBe(beforeRuns);
    expect(runCreatedEventCount()).toBe(beforeRunCreatedEvents);
  });

  it("rejects unknown selected skills on threaded compatibility create-run endpoints", async () => {
    const beforeRuns = getRuntime().store.listRuns({}).length;
    const beforeRunCreatedEvents = runCreatedEventCount();
    const res = await app.inject({
      method: "POST",
      url: "/api/threads/thread_missing_skill_create/runs",
      payload: {
        task_msg: "Use a missing skill",
        org_id: "org_1",
        actor_user_id: "user_1",
        selected_skill_keys: ["missing-skill"],
      },
    });

    expect(res.statusCode).toBe(400);
    expect(JSON.parse(res.body)).toEqual({ error: "Skill not found: missing-skill" });
    expect(getRuntime().store.listRuns({}).length).toBe(beforeRuns);
    expect(runCreatedEventCount()).toBe(beforeRunCreatedEvents);
  });

  it("rejects unknown selected skills on compatibility stream create-run endpoints", async () => {
    const beforeRuns = getRuntime().store.listRuns({}).length;
    const beforeRunCreatedEvents = runCreatedEventCount();

    const root = await app.inject({
      method: "POST",
      url: "/api/runs/stream",
      payload: {
        task_msg: "Use a missing skill",
        org_id: "org_1",
        actor_user_id: "user_1",
        selected_skill_keys: ["missing-skill"],
      },
    });

    expect(root.statusCode).toBe(400);
    expect(JSON.parse(root.body)).toEqual({ error: "Skill not found: missing-skill" });
    expect(getRuntime().store.listRuns({}).length).toBe(beforeRuns);
    expect(runCreatedEventCount()).toBe(beforeRunCreatedEvents);

    const threaded = await app.inject({
      method: "POST",
      url: "/api/threads/thread_missing_skill_stream/runs/stream",
      payload: {
        task_msg: "Use a missing skill",
        org_id: "org_1",
        actor_user_id: "user_1",
        selected_skill_keys: ["missing-skill"],
      },
    });

    expect(threaded.statusCode).toBe(400);
    expect(JSON.parse(threaded.body)).toEqual({ error: "Skill not found: missing-skill" });
    expect(getRuntime().store.listRuns({}).length).toBe(beforeRuns);
    expect(runCreatedEventCount()).toBe(beforeRunCreatedEvents);
  });

  it("wakes up an existing queued frontend chat run when its stream is opened", async () => {
    const runtime = getRuntime();
    const run: AgentRun = {
      id: "run_stream_wakeup",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "chat",
      thread_id: null,
      workspace_id: "ws_stream_wakeup",
      task_msg: "wake me",
      scopes: ["agent.workspace.read"],
      harness_options: { model_profile_key: "test-chat" } as any,
      status: "queued",
      current_approval_id: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    };
    runtime.store.createRun(run);
    runtime.eventWriter.write(run.id, null, "run.created", {
      run_id: run.id,
      status: "queued",
    });

    const stream = await app.inject({
      method: "GET",
      url: `/api/runs/${run.id}/stream?follow=true&after_sequence=1`,
    });
    expect(stream.statusCode).toBe(200);
    expect(stream.body).not.toContain('"sequence":1');

    const events = await waitForRunEvents(run.id, "run.completed");
    expect(events.map((event: any) => event.type)).toContain("message.completed");
  });

  it("records user input for waiting clarification runs", async () => {
    const runtime = getRuntime();
    runtime.store.createThread({
      id: "thread_input_resume",
      org_id: "org_input",
      owner_user_id: "user_1",
      title: "Input",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    runtime.store.createRun({
      id: "run_input_resume",
      org_id: "org_input",
      actor_user_id: "user_1",
      source: "chat",
      thread_id: "thread_input_resume",
      workspace_id: "ws_input_resume",
      task_msg: "clarify",
      scopes: ["agent.input.write"],
      harness_options: null,
      status: "waiting_input",
      current_approval_id: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    });

    const res = await app.inject({
      method: "POST",
      url: "/api/runs/run_input_resume/input",
      payload: { content: "Use /a.md" },
    });

    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).status).toBe("queued");
    expect(runtime.store.listMessages("thread_input_resume").at(-1)?.content).toBe("Use /a.md");
    expect(runtime.store.listEvents("run_input_resume").map((event) => event.type)).toEqual(
      expect.arrayContaining(["message.completed", "input.received", "run.resumed"]),
    );
    runtime.store.updateThread("thread_input_resume", { updated_at: "2025-01-01T00:00:00Z" });
    runtime.store.updateRun("run_input_resume", { started_at: "2025-01-01T00:00:00Z" });
  });

  it("resumes waiting clarification runs with a native tool result", async () => {
    const runtime = getRuntime();
    runtime.store.createThread({
      id: "thread_input_formal",
      org_id: "org_input",
      owner_user_id: "user_1",
      title: "Input formal",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    runtime.store.createRun({
      id: "run_input_formal",
      org_id: "org_input",
      actor_user_id: "user_1",
      source: "chat",
      thread_id: "thread_input_formal",
      workspace_id: "ws_input_formal",
      task_msg: "clarify",
      scopes: ["agent.input.write"],
      harness_options: null,
      status: "waiting_input",
      current_approval_id: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    });
    createToolCallRecord(runtime.store, {
      id: "clarify_tc_formal",
      run_id: "run_input_formal",
      tool_name: "ask_clarification",
      input: { question: "Which file?" },
      status: "completed",
      output: { input_request_id: "clarify_run_input_formal_clarify_tc_formal" },
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    runtime.eventWriter.write("run_input_formal", "thread_input_formal", EVENT_TYPES.INPUT_REQUESTED, {
      input_request_id: "clarify_run_input_formal_clarify_tc_formal",
      tool_call_id: "clarify_tc_formal",
      prompt: "Which file?",
    });

    const res = await app.inject({
      method: "POST",
      url: "/api/runs/run_input_formal/input",
      payload: {
        input_request_id: "clarify_run_input_formal_clarify_tc_formal",
        response: "Use /a.md",
      },
    });

    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).status).toBe("queued");
    const received = runtime.store
      .listEvents("run_input_formal")
      .find((event) => event.type === EVENT_TYPES.INPUT_RECEIVED);
    expect(received?.payload).toMatchObject({
      input_request_id: "clarify_run_input_formal_clarify_tc_formal",
      content: "Use /a.md",
      tool_call_id: "clarify_tc_formal",
    });
    runtime.store.updateThread("thread_input_formal", { updated_at: "2025-01-01T00:00:00Z" });
    runtime.store.updateRun("run_input_formal", { started_at: "2025-01-01T00:00:00Z" });
  });

  it("rejects mismatched clarification input request ids", async () => {
    const runtime = getRuntime();
    runtime.store.createThread({
      id: "thread_input_mismatch",
      org_id: "org_input",
      owner_user_id: "user_1",
      title: "Input mismatch",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    runtime.store.createRun({
      id: "run_input_mismatch",
      org_id: "org_input",
      actor_user_id: "user_1",
      source: "chat",
      thread_id: "thread_input_mismatch",
      workspace_id: "ws_input_mismatch",
      task_msg: "clarify",
      scopes: ["agent.input.write"],
      harness_options: null,
      status: "waiting_input",
      current_approval_id: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    });
    runtime.eventWriter.write("run_input_mismatch", "thread_input_mismatch", EVENT_TYPES.INPUT_REQUESTED, {
      input_request_id: "clarify_expected",
      tool_call_id: "clarify_tc_mismatch",
      prompt: "Which file?",
    });

    const res = await app.inject({
      method: "POST",
      url: "/api/runs/run_input_mismatch/input",
      payload: { input_request_id: "clarify_wrong", response: "Use /a.md" },
    });

    expect(res.statusCode).toBe(400);
    expect(JSON.parse(res.body).error).toContain("input_request_id");
    expect(runtime.store.getRun("run_input_mismatch")?.status).toBe("waiting_input");
    runtime.store.updateThread("thread_input_mismatch", { updated_at: "2025-01-01T00:00:00Z" });
    runtime.store.updateRun("run_input_mismatch", { started_at: "2025-01-01T00:00:00Z" });
  });

  it("projects model usage events through the compatibility API", async () => {
    const runtime = getRuntime();
    const run: AgentRun = {
      id: "run_usage_api",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "api",
      thread_id: null,
      workspace_id: "ws_usage_api",
      task_msg: "usage",
      scopes: ["*"],
      harness_options: null,
      status: "completed",
      current_approval_id: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:00:01Z",
      claim: null,
      result: null,
      error: null,
    };
    runtime.store.createRun(run);
    runtime.eventWriter.write(run.id, null, "model.usage", {
      requests: 2,
      input_tokens: 18,
      output_tokens: 4,
      total_tokens: 22,
    });

    const res = await app.inject({
      method: "GET",
      url: `/api/runs/${run.id}/usage`,
    });

    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body)).toMatchObject({
      run_id: run.id,
      own_requests: 2,
      own_input_tokens: 18,
      own_output_tokens: 4,
      own_total_tokens: 22,
      total_requests: 2,
      total_tokens: 22,
    });
  });

  it("returns dashboard conversations with newest activity first", async () => {
    const runtime = getRuntime();
    runtime.store.createThread({
      id: "thread_dashboard_old",
      org_id: "org_1",
      owner_user_id: "user_1",
      title: "Old dashboard thread",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    runtime.store.createThread({
      id: "thread_dashboard_new",
      org_id: "org_1",
      owner_user_id: "user_1",
      title: "New dashboard thread",
      status: "active",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });

    const res = await app.inject({
      method: "GET",
      url: "/api/threads/dashboard?limit=2",
    });

    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).items.map((item: any) => item.thread.id)).toEqual([
      "thread_dashboard_new",
      "thread_dashboard_old",
    ]);
  });

  it("cancel returns the updated run shape", async () => {
    const created = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "org_1",
        actor_user_id: "user_1",
        source: "chat",
        task_msg: "cancel me",
      },
    });
    const run = JSON.parse(created.body);

    const cancelled = await app.inject({
      method: "POST",
      url: `/api/runs/${run.id}/cancel`,
    });

    expect(cancelled.statusCode).toBe(200);
    const body = JSON.parse(cancelled.body);
    expect(body.id).toBe(run.id);
    expect(body.status).toBe("cancelled");
  });

  it("exposes built-in skills and tool configs to the settings UI", async () => {
    const [registry, skills, tools] = await Promise.all([
      app.inject({ method: "GET", url: "/api/skill-registry" }),
      app.inject({ method: "GET", url: "/api/skills" }),
      app.inject({ method: "GET", url: "/api/external-tools/configs" }),
    ]);

    expect(registry.statusCode).toBe(200);
    expect(skills.statusCode).toBe(200);
    expect(tools.statusCode).toBe(200);

    const registryBody = JSON.parse(registry.body);
    const skillsBody = JSON.parse(skills.body);
    const toolsBody = JSON.parse(tools.body);

    expect(registryBody.length).toBeGreaterThanOrEqual(10);
    expect(skillsBody.length).toBeGreaterThanOrEqual(10);
    expect(toolsBody.length).toBeGreaterThan(0);
    expect(registryBody.map((entry: any) => entry.key)).toEqual(
      expect.arrayContaining(["deep-research", "frontend-design", "skill-creator"]),
    );
    expect(skillsBody.map((skill: any) => skill.key)).toEqual(
      expect.arrayContaining(["deep-research", "frontend-design", "skill-creator"]),
    );
    expect(toolsBody[0].provider_kind).toBe("mcp");
    expect(toolsBody[0].mcp.tools.length).toBeGreaterThan(0);
  });

  it("routes stored MCP configs through the production capability router", async () => {
    const secretRef = "secret://external-tools/org_1/runtime-search/api-key";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ jsonrpc: "2.0", id: "mcp_test", result: { answer: "found" } }),
    } as unknown as Response);

    try {
      getRuntime().store.setSecret("org_1", secretRef, "mcp-secret");
      const created = await app.inject({
        method: "POST",
        url: "/api/external-tools/configs",
        payload: {
          key: "runtime-search",
          provider_kind: "mcp",
          name: "Runtime Search",
          enabled: true,
          mcp: {
            server_key: "runtime-search",
            name: "Runtime Search",
            endpoint: {
              url: "https://search.example.com/mcp",
              allowed_hosts: ["search.example.com"],
              auth_secret: { secret_ref: secretRef },
            },
            tools: [
              {
                name: "mcp.runtime_search",
                description: "Search via configured MCP server",
                input_schema: { type: "object" },
                risk_level: "low",
                required_scopes: ["web:read"],
                approval_policy: "never",
              },
            ],
          },
        },
      });
      expect(created.statusCode).toBe(201);

      const run: AgentRun = {
        id: "run_mcp_runtime",
        org_id: "org_1",
        actor_user_id: "user_1",
        source: "chat",
        thread_id: null,
        workspace_id: "ws_mcp_runtime",
        task_msg: "search",
        scopes: ["web:read"],
        harness_options: null,
        status: "queued",
        current_approval_id: null,
        started_at: "2026-01-01T00:00:00Z",
        completed_at: null,
        claim: null,
        result: null,
        error: null,
      };
      const otherOrgRun: AgentRun = {
        ...run,
        id: "run_mcp_runtime_other_org",
        org_id: "org_2",
        actor_user_id: "user_2",
        workspace_id: "ws_mcp_runtime_other_org",
      };
      getRuntime().store.createRun(run);
      getRuntime().store.createRun(otherOrgRun);

      const tools = await getRuntime().capabilityRouter.listTools({ run });
      const otherOrgTools = await getRuntime().capabilityRouter.listTools({ run: otherOrgRun });
      const prepared = await getRuntime().capabilityRouter.prepareToolCall(
        { id: "tc_mcp_runtime_prepare", run_id: run.id, name: "mcp.runtime_search", input: {} },
        { run },
      );
      const result = await getRuntime().capabilityRouter.executeToolCall(
        { id: "tc_mcp_runtime", run_id: run.id, name: "mcp.runtime_search", input: { query: "x" } },
        { run },
      );
      const otherOrgPrepared = await getRuntime().capabilityRouter.prepareToolCall(
        { id: "tc_mcp_runtime_other_org_prepare", run_id: otherOrgRun.id, name: "mcp.runtime_search", input: {} },
        { run: otherOrgRun },
      );

      expect(tools.map((tool) => tool.name)).toContain("mcp.runtime_search");
      expect(otherOrgTools.map((tool) => tool.name)).not.toContain("mcp.runtime_search");
      expect(prepared).toMatchObject({ allowed: true, requires_approval: false });
      expect(otherOrgPrepared).toMatchObject({ allowed: false, reason: "Unknown tool: mcp.runtime_search" });
      expect(result.output).toEqual({ answer: "found" });
      expect(fetchMock.mock.calls[0][0]).toBe("https://search.example.com/mcp");
      expect((fetchMock.mock.calls[0][1]?.headers as Record<string, string>).authorization).toBe("Bearer mcp-secret");
    } finally {
      fetchMock.mockRestore();
    }
  });

  it("does not expose deleted artifact backend routes", () => {
    expect(app.hasRoute({ method: "GET", url: "/api/artifacts" })).toBe(false);
    expect(
      app.hasRoute({ method: "POST", url: "/api/runs/:run_id/export/artifact" }),
    ).toBe(false);
  });
});

describe("database-backed settings compatibility", () => {
  let tempDir: string;
  let dbPath: string;

  beforeAll(() => {
    tempDir = mkdtempSync(join(tmpdir(), "aithru-agent-api-"));
    dbPath = join(tempDir, "agent.sqlite");
  });

  afterAll(() => {
    resetRuntimeForTests();
    rmSync(tempDir, { recursive: true, force: true });
  });

  it("persists model profiles and redacted secrets in SQLite", async () => {
    resetRuntimeForTests();
    let app = await createApp({ dbPath });
    await app.ready();

    const created = await app.inject({
      method: "POST",
      url: "/api/model-profiles",
      payload: {
        key: "custom-deepseek-v4-flash",
        name: "DeepSeek V4 Flash",
        provider: "custom",
        model: "custom:DeepSeekv4 flash",
        enabled: true,
        capabilities: { vision: false, thinking: false },
        cost_policy: {},
        selection_policy: { required_scopes: [] },
        auth_secret: { write_only_value: "sk-test-secret" },
        metadata: { base_url: "https://api.deepseek.com/v1" },
      },
    });

    expect(created.statusCode).toBe(201);
    expect(created.body).not.toContain("sk-test-secret");
    const createdBody = JSON.parse(created.body);
    expect(createdBody.auth_secret).toEqual({
      has_secret: true,
      secret_ref: "secret://model-profiles/org_1/custom-deepseek-v4-flash/api-key",
      redacted: true,
    });

    await app.close();
    resetRuntimeForTests();
    app = await createApp({ dbPath });
    await app.ready();

    const detail = await app.inject({
      method: "GET",
      url: "/api/model-profiles/custom-deepseek-v4-flash",
    });
    const secretRef =
      "secret://model-profiles/org_1/custom-deepseek-v4-flash/api-key";

    expect(detail.statusCode).toBe(200);
    expect(detail.body).not.toContain("sk-test-secret");
    expect(JSON.parse(detail.body).model).toBe("custom:DeepSeekv4 flash");
    expect(getRuntime().store.getSecret("org_1", secretRef)).toBe("sk-test-secret");
    await app.close();
  });

  it("persists external tool and skill settings in SQLite", async () => {
    resetRuntimeForTests();
    const app = await createApp({ dbPath });
    await app.ready();

    const external = await app.inject({
      method: "POST",
      url: "/api/external-tools/configs",
      payload: {
        key: "search",
        provider_kind: "mcp",
        name: "Search",
        enabled: true,
        mcp: {
          server_key: "search",
          name: "Search",
          endpoint: {
            url: "https://search.example.com/mcp",
            allowed_hosts: ["search.example.com"],
            timeout_ms: 5000,
            max_response_bytes: 100000,
            auth_secret: { secret_ref: "secret://external-tools/org_1/search/api-key" },
          },
          tools: [
            {
              name: "query",
              description: "Search",
              input_schema: { type: "object" },
              output_schema: { type: "object" },
              risk_level: "low",
              required_scopes: ["web:read"],
              approval_policy: "never",
              failure_policy: "fail_run",
            },
          ],
        },
      },
    });
    const skill = await app.inject({
      method: "PATCH",
      url: "/api/skill-registry/deep-research",
      payload: { enabled: false },
    });

    expect(external.statusCode).toBe(201);
    expect(skill.statusCode).toBe(200);
    await app.close();

    resetRuntimeForTests();
    const reloaded = await createApp({ dbPath });
    await reloaded.ready();
    const externalDetail = await reloaded.inject({
      method: "GET",
      url: "/api/external-tools/configs/search",
    });
    const skillDetail = await reloaded.inject({
      method: "GET",
      url: "/api/skill-registry/deep-research",
    });

    expect(externalDetail.statusCode).toBe(200);
    expect(JSON.parse(externalDetail.body).mcp.endpoint.auth_secret.has_secret).toBe(true);
    expect(skillDetail.statusCode).toBe(200);
    expect(JSON.parse(skillDetail.body).enabled).toBe(false);
    await reloaded.close();
  });
});
