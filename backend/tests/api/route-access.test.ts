import Fastify, { type FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createRuntime, getRuntime, resetRuntimeForTests } from "../../apps/api/src/runtime.js";
import { registerApprovalRoutes } from "../../apps/api/src/routes/approvals.js";
import { registerCompatRoutes } from "../../apps/api/src/routes/compat.js";
import { registerRunRoutes } from "../../apps/api/src/routes/runs.js";
import type { AgentRun } from "@aithru-agent/contracts";

const actor = {
  actorType: "user" as const,
  userId: "user_1",
  orgId: "org_1",
  scopes: ["agent.app.runs.read", "agent.app.runs.execute", "agent.app.runs.cancel", "agent.app.approvals.resolve"],
  roles: [],
  tokenType: "hosted_access" as const,
  claims: {},
};

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function run(id: string, actor_user_id = "user_2"): AgentRun {
  return {
    id,
    org_id: "org_1",
    actor_user_id,
    source: "chat",
    thread_id: "thread_foreign",
    workspace_id: "ws_thread_thread_foreign",
    task_msg: "foreign run",
    scopes: ["*"],
    harness_options: null,
    status: "queued",
    current_approval_id: null,
    started_at: now(),
    completed_at: null,
    claim: null,
    result: null,
    error: null,
  };
}

async function appWithActor(register: (app: FastifyInstance) => void): Promise<FastifyInstance> {
  resetRuntimeForTests();
  await createRuntime();
  const app = Fastify({ logger: false });
  app.addHook("preHandler", async (request) => {
    (request as any).aithruActor = actor;
  });
  register(app);
  await app.ready();
  return app;
}

describe("authenticated route resource access", () => {
  let app: FastifyInstance | null = null;

  beforeEach(() => {
    resetRuntimeForTests();
  });

  afterEach(async () => {
    await app?.close();
    resetRuntimeForTests();
    app = null;
  });

  it("rejects creating a run attached to another user's thread before mutating state", async () => {
    app = await appWithActor(registerRunRoutes);
    getRuntime().store.createThread({
      id: "thread_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      title: "Foreign",
      status: "active",
      created_at: now(),
      updated_at: now(),
    });

    const response = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "spoofed_org",
        actor_user_id: "spoofed_user",
        thread_id: "thread_foreign",
        task_msg: "write into foreign thread",
        persist_task_msg_message: true,
      },
    });

    expect(response.statusCode).toBe(403);
    expect(getRuntime().store.listRuns({ thread_id: "thread_foreign" })).toEqual([]);
    expect(getRuntime().store.listMessages("thread_foreign")).toEqual([]);
  });

  it("rejects compat reads, streams, and cancels for another user's run", async () => {
    app = await appWithActor(registerCompatRoutes);
    getRuntime().store.createThread({
      id: "thread_foreign",
      org_id: "org_1",
      owner_user_id: "user_2",
      title: "Foreign",
      status: "active",
      created_at: now(),
      updated_at: now(),
    });
    getRuntime().store.createRun(run("run_foreign"));

    const thread = await app.inject({ method: "GET", url: "/api/threads/thread_foreign" });
    const stream = await app.inject({ method: "GET", url: "/api/threads/thread_foreign/runs/run_foreign/stream" });
    const cancel = await app.inject({ method: "POST", url: "/api/threads/thread_foreign/runs/run_foreign/cancel" });

    expect(thread.statusCode).toBe(403);
    expect(stream.statusCode).toBe(403);
    expect(cancel.statusCode).toBe(403);
    expect(getRuntime().store.getRun("run_foreign")?.status).toBe("queued");
  });

  it("rejects resolving another user's approval before changing approval status", async () => {
    app = await appWithActor(registerApprovalRoutes);
    getRuntime().store.createRun(run("run_approval"));
    getRuntime().store.createApproval({
      id: "approval_foreign",
      run_id: "run_approval",
      tool_call_id: "tc_foreign",
      tool_name: "workspace.write_file",
      status: "pending",
      created_at: now(),
    });

    const response = await app.inject({
      method: "POST",
      url: "/api/approvals/approval_foreign/resolve",
      payload: { decision: "approved" },
    });

    expect(response.statusCode).toBe(403);
    expect(getRuntime().store.getApproval("approval_foreign")?.status).toBe("pending");
  });
});
