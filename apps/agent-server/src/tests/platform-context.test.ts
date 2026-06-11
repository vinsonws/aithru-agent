import { describe, it, expect, beforeAll, afterAll } from "vitest";
import type { Server, IncomingMessage, ServerResponse } from "node:http";
import { createAgentServerRuntime } from "../runtime/create-agent-server-runtime.js";
import { createAgentHttpServer } from "../server/create-agent-http-server.js";
import { handleRequest } from "../server/routes.js";
import type { AgentHttpContext } from "../server/context.js";

// ── Helpers ────────────────────────────────────────────────────────────────

type FetchResult = { status: number; body: unknown };

async function fetchJson(url: string, options?: RequestInit): Promise<FetchResult> {
  const res = await fetch(url, options);
  const body = await res.json();
  return { status: res.status, body };
}

function wait(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// Build a fake platform-mode AgentHttpContext for testing
function createFakePlatformContext(overrides?: {
  orgId?: string;
  userId?: string;
  scopes?: string[];
  requireScope?: (scope: string) => void | Promise<void>;
  registerResource?: (input: Record<string, unknown>) => void;
  auditSuccess?: (action: string, input?: Record<string, unknown>) => void;
  auditFailure?: (action: string, input?: Record<string, unknown>) => void;
}): AgentHttpContext {
  return {
    mode: "platform",
    actor: {
      actorType: "user",
      userId: overrides?.userId ?? "user_from_token",
      orgId: overrides?.orgId ?? "org_from_token",
      scopes: overrides?.scopes ?? [
        "agent.run.create", "agent.run.read", "agent.run.cancel",
        "agent.approval.resolve", "agent.thread.write",
        "agent.approval.read", "agent.app.view",
      ],
      roles: ["agent.operator"],
      audience: "agent",
      tokenType: "access",
    },
    requireScope(scope: string): void {
      if (overrides?.requireScope) {
        return overrides.requireScope(scope) as void;
      }
      const actor = this.actor!;
      if (!actor.scopes.includes(scope)) {
        const err = new Error(`Missing required scope: ${scope}`);
        err.name = "AithruAuthzDeniedError";
        throw err;
      }
    },
    async auditSuccess(
      action: string,
      _input?: { targetType?: string; targetId?: string; metadata?: Record<string, unknown> },
    ): Promise<void> {
      if (overrides?.auditSuccess) {
        overrides.auditSuccess(action, _input as Record<string, unknown>);
      }
    },
    async auditFailure(
      action: string,
      _input?: { targetType?: string; targetId?: string; error?: unknown; metadata?: Record<string, unknown> },
    ): Promise<void> {
      if (overrides?.auditFailure) {
        overrides.auditFailure(action, _input as Record<string, unknown>);
      }
    },
    async registerResource(input: {
      orgId: string;
      resourceType: string;
      resourceId: string;
      displayName: string;
      ownerUserId?: string;
      metadata?: Record<string, unknown>;
    }): Promise<void> {
      if (overrides?.registerResource) {
        overrides.registerResource(input as Record<string, unknown>);
      }
    },
  };
}

// ── Suite ──────────────────────────────────────────────────────────────────

describe("platform-context", () => {
  let server: Server;
  let baseUrl: string;
  let rt: ReturnType<typeof createAgentServerRuntime>;

  beforeAll(async () => {
    rt = createAgentServerRuntime();
    server = createAgentHttpServer(rt);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const addr = server.address();
    if (!addr || typeof addr === "string") {
      throw new Error("Could not determine server address");
    }
    baseUrl = `http://127.0.0.1:${addr.port}`;
  });

  afterAll(async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  // ── Test A: Standalone create run trusts body ────────────────────────────

  it("standalone should trust body identity", async () => {
    const { status, body } = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        goal: "Standalone identity test.",
        orgId: "custom_org",
        actorUserId: "custom_user",
        scopes: ["*"],
      }),
    });

    expect(status).toBe(201);

    const bodyRecord = body as Record<string, unknown>;
    const runId = bodyRecord.runId as string;
    await wait(200);

    const { body: runBody } = await fetchJson(`${baseUrl}/runs/${runId}`);
    const runRecord = runBody as Record<string, unknown>;

    // In standalone mode, body identity should be preserved
    expect(runRecord.orgId).toBe("custom_org");
    expect(runRecord.actorUserId).toBe("custom_user");
  });

  // ── Test B: Platform create run ignores body identity ────────────────────

  it("platform should ignore body identity and use actor from context", async () => {
    // Direct call to handleRequest with fake platform context
    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();

    const req = createMockRequest("POST", "/runs", {
      goal: "Platform identity test.",
      orgId: "evil_org",
      actorUserId: "evil_user",
      scopes: ["*"],
    });
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    const ctx = createFakePlatformContext({
      orgId: "org_from_token",
      userId: "user_from_token",
    });

    await handleRequest(req, res, rt, ctx);
    const result = await promise;

    expect(result.statusCode).toBe(201);
    const bodyRecord = result.body as Record<string, unknown>;
    const runId = bodyRecord.runId as string;

    // Wait for projection
    await wait(200);

    const { body: runBody } = await fetchJson(`${baseUrl}/runs/${runId}`);
    const runRecord = runBody as Record<string, unknown>;

    // Identity should come from token/context, not body
    expect(runRecord.orgId).toBe("org_from_token");
    expect(runRecord.actorUserId).toBe("user_from_token");

    // Evil values should NOT be in the projection
    expect(runRecord.orgId).not.toBe("evil_org");
    expect(runRecord.actorUserId).not.toBe("evil_user");
  });

  it("platform should map platform workspace permissions to harness tool scopes", async () => {
    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("POST", "/runs", {
      goal: "Platform scope mapping test.",
    });
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    const ctx = createFakePlatformContext({
      scopes: ["agent.run.create", "agent.workspace.write"],
    });

    await handleRequest(req, res, rt, ctx);
    const result = await promise;

    expect(result.statusCode).toBe(201);
    const bodyRecord = result.body as Record<string, unknown>;
    const runId = bodyRecord.runId as string;

    await waitForStatus(baseUrl, runId, "waiting_approval");
  });

  it("platform create run should return mounted API URLs", async () => {
    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("POST", "/runs", {
      goal: "Platform URL prefix test.",
    });
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    await handleRequest(req, res, rt, createFakePlatformContext());
    const result = await promise;

    expect(result.statusCode).toBe(201);
    expect(result.body).toMatchObject({
      eventsUrl: expect.stringMatching(/^\/api\/agent\/runs\/.+\/events$/),
      streamUrl: expect.stringMatching(/^\/api\/agent\/runs\/.+\/stream$/),
    });
  });

  it("platform run reads should be scoped to actor org", async () => {
    const { body: foreignCreateBody } = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        goal: "Foreign org run.",
        orgId: "foreign_org",
        actorUserId: "foreign_user",
        scopes: ["*"],
      }),
    });
    const foreignRunId = (foreignCreateBody as Record<string, unknown>).runId as string;

    const ctx = createFakePlatformContext({
      orgId: "org_from_token",
      scopes: ["agent.run.read"],
    });

    const list = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    await handleRequest(
      createMockRequest("GET", "/runs"),
      createMockResponse((statusCode, body) => list.resolve({ statusCode, body })),
      rt,
      ctx,
    );
    const listResult = await list.promise;

    expect(listResult.statusCode).toBe(200);
    const runs = listResult.body as Array<Record<string, unknown>>;
    expect(runs.every((run) => run.orgId === "org_from_token")).toBe(true);
    expect(runs.some((run) => run.id === foreignRunId)).toBe(false);

    const get = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    await handleRequest(
      createMockRequest("GET", `/runs/${foreignRunId}`),
      createMockResponse((statusCode, body) => get.resolve({ statusCode, body })),
      rt,
      ctx,
    );
    const getResult = await get.promise;

    expect(getResult.statusCode).toBe(404);
  });

  // ── Test C: Missing scope denies ─────────────────────────────────────────

  it("platform should deny when required scope is missing", async () => {
    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("POST", "/runs", {
      goal: "Scope denied test.",
    });
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    // Context with NO agent.run.create scope
    const ctx = createFakePlatformContext({
      scopes: ["agent.app.view"], // no agent.run.create
    });

    await handleRequest(req, res, rt, ctx);
    const result = await promise;

    expect(result.statusCode).toBe(403);
    const errorBody = result.body as Record<string, unknown>;
    expect(errorBody).toHaveProperty("error");
    expect((errorBody.error as Record<string, unknown>).code).toBe("AITHRU_AUTHZ_DENIED");
  });

  it("platform should await asynchronous scope checks before handling requests", async () => {
    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("POST", "/runs", {
      goal: "Async authz should fail closed.",
    });
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    const ctx = createFakePlatformContext({
      async requireScope(scope: string): Promise<void> {
        await wait(10);
        const err = new Error(`Missing required scope: ${scope}`);
        err.name = "AithruAuthzDeniedError";
        throw err;
      },
    });

    await handleRequest(req, res, rt, ctx);
    const result = await promise;

    expect(result.statusCode).toBe(403);
    const errorBody = result.body as Record<string, unknown>;
    expect((errorBody.error as Record<string, unknown>).code).toBe("AITHRU_AUTHZ_DENIED");
  });

  // ── Test D: /me returns actor ────────────────────────────────────────────

  it("platform /me should return actor from context", async () => {
    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("GET", "/me");
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    const ctx = createFakePlatformContext({
      orgId: "org_me_test",
      userId: "user_me_test",
      scopes: ["agent.app.view"],
    });

    await handleRequest(req, res, rt, ctx);
    const result = await promise;

    expect(result.statusCode).toBe(200);
    const bodyRecord = result.body as Record<string, unknown>;
    expect(bodyRecord.mode).toBe("platform");
    expect(bodyRecord.actor).toBeTruthy();
    const actor = bodyRecord.actor as Record<string, unknown>;
    expect(actor.orgId).toBe("org_me_test");
    expect(actor.userId).toBe("user_me_test");
    expect(actor.actorType).toBe("user");
  });

  it("standalone /me should return mode standalone with null actor", async () => {
    const { status, body } = await fetchJson(`${baseUrl}/me`);
    expect(status).toBe(200);
    const result = body as Record<string, unknown>;
    expect(result.mode).toBe("standalone");
    expect(result.actor).toBeNull();
  });

  // ── Test E: Resource registration callback ───────────────────────────────

  it("platform should call registerResource on create thread", async () => {
    const calledResources: Record<string, unknown>[] = [];

    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("POST", "/threads", {
      title: "Resource reg test",
    });
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    const ctx = createFakePlatformContext({
      registerResource(input: Record<string, unknown>) {
        calledResources.push(input);
      },
    });

    await handleRequest(req, res, rt, ctx);
    const result = await promise;

    expect(result.statusCode).toBe(201);
    expect(calledResources.length).toBeGreaterThanOrEqual(1);
    const resource = calledResources[0]!;
    expect(resource.resourceType).toBe("thread");
    expect(resource.orgId).toBe("org_from_token");
    expect(resource.ownerUserId).toBe("user_from_token");
  });

  it("platform should call registerResource on create run", async () => {
    const calledResources: Record<string, unknown>[] = [];

    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("POST", "/runs", {
      goal: "Resource reg test run.",
    });
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    const ctx = createFakePlatformContext({
      registerResource(input: Record<string, unknown>) {
        calledResources.push(input);
      },
    });

    await handleRequest(req, res, rt, ctx);
    const result = await promise;

    expect(result.statusCode).toBe(201);
    expect(calledResources.length).toBeGreaterThanOrEqual(1);
    const resource = calledResources[0]!;
    expect(resource.resourceType).toBe("run");
    expect(resource.orgId).toBe("org_from_token");
    expect(resource.ownerUserId).toBe("user_from_token");
  });

  // ── Test F: Audit callback called ────────────────────────────────────────

  it("platform should call auditSuccess on create run", async () => {
    const auditCalls: { action: string; input?: unknown }[] = [];

    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("POST", "/runs", {
      goal: "Audit test run.",
    });
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    const ctx = createFakePlatformContext({
      orgId: "org_1",
      auditSuccess(action: string, input?: Record<string, unknown>) {
        auditCalls.push({ action, input });
      },
    });

    await handleRequest(req, res, rt, ctx);
    await promise;

    expect(auditCalls.length).toBeGreaterThanOrEqual(1);
    const audit = auditCalls.find((a) => a.action === "agent.run.create");
    expect(audit).toBeTruthy();
    expect(audit!.action).toBe("agent.run.create");
  });

  it("platform should call auditSuccess on cancel run", async () => {
    // First, create a run and wait for it to pause
    const { body: createBody } = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ goal: "Cancel audit test.", scopes: ["*"] }),
    });
    const createRecord = createBody as Record<string, unknown>;
    const runId = createRecord.runId as string;

    // Wait for the run to pause
    await waitForStatus(baseUrl, runId, "waiting_approval");

    const auditCalls: { action: string; input?: unknown }[] = [];

    // Now cancel via handleRequest with platform context
    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("POST", `/runs/${runId}/cancel`);
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    const ctx = createFakePlatformContext({
      orgId: "org_1",
      auditSuccess(action: string, input?: Record<string, unknown>) {
        auditCalls.push({ action, input });
      },
      auditFailure(action: string, input?: Record<string, unknown>) {
        auditCalls.push({ action, input });
      },
    });

    await handleRequest(req, res, rt, ctx);
    await promise;

    expect(auditCalls.length).toBeGreaterThanOrEqual(1);
    const audit = auditCalls.find((a) => a.action === "agent.run.cancel");
    expect(audit).toBeTruthy();
  });

  it("platform should call auditSuccess on approval resolve", async () => {
    // Create a run
    const { body: createBody } = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ goal: "Approval audit test.", scopes: ["*"] }),
    });
    const createRecord = createBody as Record<string, unknown>;
    const runId = createRecord.runId as string;

    // Wait for pause
    await waitForStatus(baseUrl, runId, "waiting_approval");

    // Get approval
    const approvalsRes = await fetch(`${baseUrl}/approvals?status=pending`);
    const approvals = await approvalsRes.json() as Record<string, unknown>[];
    const approval = approvals.find((a) => a.runId === runId) as Record<string, unknown>;
    const approvalId = approval.id as string;

    const auditCalls: { action: string; input?: unknown }[] = [];

    // Resolve via handleRequest with platform context
    const { promise, resolve } = createPromiseWithResolvers<{ statusCode: number; body: unknown }>();
    const req = createMockRequest("POST", `/approvals/${approvalId}/resolve`, {
      decision: "approved",
    });
    const res = createMockResponse((statusCode: number, responseBody: unknown) => {
      resolve({ statusCode, body: responseBody });
    });

    const ctx = createFakePlatformContext({
      orgId: "org_1",
      auditSuccess(action: string, input?: Record<string, unknown>) {
        auditCalls.push({ action, input });
      },
    });

    await handleRequest(req, res, rt, ctx);
    await promise;

    expect(auditCalls.length).toBeGreaterThanOrEqual(1);
    const audit = auditCalls.find((a) => a.action === "agent.approval.resolve");
    expect(audit).toBeTruthy();
  });
});

// ── Helpers ────────────────────────────────────────────────────────────────

async function waitForStatus(
  baseUrl: string,
  runId: string,
  expectedStatus: string,
  timeoutMs = 8000,
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const res = await fetch(`${baseUrl}/runs/${runId}`);
    const run = await res.json() as Record<string, unknown>;
    if (run.status === expectedStatus) return;
    await wait(100);
  }
  throw new Error(`Timeout waiting for status ${expectedStatus}`);
}

function createMockRequest(
  method: string,
  url: string,
  body?: Record<string, unknown>,
): IncomingMessage {
  const chunks = body ? [Buffer.from(JSON.stringify(body))] : [];

  return {
    method,
    url,
    headers: {
      "host": "127.0.0.1",
      "content-type": body ? "application/json" : undefined,
      "content-length": body ? String(Buffer.byteLength(JSON.stringify(body))) : "0",
    },
    on(event: string, handler: (...args: unknown[]) => void) {
      if (event === "data" && chunks.length > 0) {
        handler(chunks[0]);
      }
      if (event === "end") {
        handler();
      }
      return this;
    },
  } as unknown as IncomingMessage;
}

function createMockResponse(
  onEnd: (statusCode: number, body: unknown) => void,
): ServerResponse {
  let statusCode = 200;
  let bodyStr = "";

  return {
    statusCode,
    writeHead(code: number) {
      statusCode = code;
      return this;
    },
    write(chunk: string | Buffer) {
      bodyStr += Buffer.isBuffer(chunk) ? chunk.toString() : chunk;
      return true;
    },
    end(chunk?: string | Buffer) {
      if (chunk) {
        bodyStr += Buffer.isBuffer(chunk) ? chunk.toString() : chunk;
      }
      try {
        onEnd(statusCode, JSON.parse(bodyStr));
      } catch {
        onEnd(statusCode, bodyStr);
      }
    },
    on() { return this; },
    once() { return this; },
    emit() { return false; },
    flushHeaders() {},
  } as unknown as ServerResponse;
}

function createPromiseWithResolvers<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
