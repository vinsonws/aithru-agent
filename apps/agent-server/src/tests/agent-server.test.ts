import { describe, it, expect, beforeAll, afterAll } from "vitest";
import type { Server } from "node:http";
import { createAgentServerRuntime } from "../runtime/create-agent-server-runtime.js";
import { createAgentHttpServer } from "../server/create-agent-http-server.js";
import { projectEventIntoStore } from "../runtime/project-event.js";
import type { AgentStreamEvent } from "@aithru/agent-stream";

// ── Helpers ────────────────────────────────────────────────────────────────

async function fetchJson(url: string, options?: RequestInit): Promise<unknown> {
  const res = await fetch(url, options);
  const body = await res.json();
  return body;
}

function wait(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitForEvents(
  baseUrl: string,
  runId: string,
  predicate: (events: AgentStreamEvent[]) => boolean,
  timeoutMs = 10000,
): Promise<AgentStreamEvent[]> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const res = await fetch(`${baseUrl}/runs/${runId}/events`);
    const events = (await res.json()) as AgentStreamEvent[];
    if (predicate(events)) return events;
    await wait(100);
  }
  // On timeout, fetch one more time for diagnostic info
  const res = await fetch(`${baseUrl}/runs/${runId}/events`);
  const events = (await res.json()) as AgentStreamEvent[];
  const types = events.map((e) => e.type).join(", ");
  throw new Error(
    `Timeout waiting for events. Got after timeout: [${types}] (${events.length} events)`,
  );
}

/** Create a run, wait for it to pause for approval, resolve the approval, and wait for completion. */
async function createAndCompleteRun(baseUrl: string, goal: string): Promise<string> {
  const createBody = await fetchJson(`${baseUrl}/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ goal, scopes: ["*"] }),
  }) as Record<string, unknown>;
  const runId = createBody.runId as string;

  // Wait for pause
  await waitForEvents(baseUrl, runId, (events) =>
    events.some((e) => e.type === "run.paused"),
  );

  // Get pending approval
  const approvals = await fetchJson(`${baseUrl}/approvals?status=pending`) as unknown[];
  const approval = (approvals as Record<string, unknown>[]).find(
    (a) => a.runId === runId,
  ) as Record<string, unknown>;

  // Resolve
  await fetchJson(`${baseUrl}/approvals/${approval.id}/resolve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ decision: "approved" }),
  });

  // Wait for completion
  await waitForEvents(baseUrl, runId, (events) =>
    events.some((e) => e.type === "run.completed"),
  );

  return runId;
}

async function waitForRunStatus(
  baseUrl: string,
  runId: string,
  expectedStatus: string,
  timeoutMs = 5000,
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const run = await fetchJson(`${baseUrl}/runs/${runId}`) as Record<string, unknown>;
    if (run.status === expectedStatus) return;
    await wait(100);
  }
  const run = await fetchJson(`${baseUrl}/runs/${runId}`) as Record<string, unknown>;
  throw new Error(
    `Timeout waiting for run status "${expectedStatus}". Last status: "${run.status}"`,
  );
}

// ── Suite ──────────────────────────────────────────────────────────────────

describe("agent-server", () => {
  let server: Server;
  let baseUrl: string;

  beforeAll(async () => {
    const rt = createAgentServerRuntime();
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

  // ── Test 1: Health ───────────────────────────────────────────────────────

  it("should return health OK", async () => {
    const body = await fetchJson(`${baseUrl}/health`) as Record<string, unknown>;
    expect(body.ok).toBe(true);
    expect(body.service).toBe("agent-server");
    expect(body.version).toBe("0.2.0-alpha.0");
  });

  // ── Test 2: Full run → approval → resume → complete ─────────────────────

  it("should create run, pause for approval, resume, and complete", async () => {
    // 2a. Create run
    const createBody = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        goal: "Analyze and write a report.",
        orgId: "org_1",
        actorUserId: "user_1",
        scopes: ["*"],
      }),
    }) as Record<string, unknown>;

    expect(createBody).toHaveProperty("runId");
    expect(createBody).toHaveProperty("status", "queued");
    expect(createBody).toHaveProperty("eventsUrl");
    expect(createBody).toHaveProperty("streamUrl");

    const runId = createBody.runId as string;
    expect(typeof runId).toBe("string");

    // 2b. Wait for run.created, run.started, approval.requested, run.paused
    const phase1Events = await waitForEvents(baseUrl, runId, (events) => {
      const types = events.map((e) => e.type);
      return (
        types.includes("run.created") &&
        types.includes("run.started") &&
        types.includes("approval.requested") &&
        types.includes("run.paused")
      );
    });

    // 2c. Get pending approval
    const approvalsBody = await fetchJson(
      `${baseUrl}/approvals?status=pending`,
    ) as unknown[];

    expect(approvalsBody.length).toBeGreaterThanOrEqual(1);
    const approval = approvalsBody[approvalsBody.length - 1] as Record<string, unknown>;
    const approvalId = approval.id as string;
    expect(approvalId).toBeTruthy();

    // 2d. Approve via POST /approvals/:id/resolve
    const resolveBody = await fetchJson(`${baseUrl}/approvals/${approvalId}/resolve`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision: "approved", comment: "Looks safe" }),
    }) as Record<string, unknown>;

    expect(resolveBody.approvalId).toBe(approvalId);
    expect(resolveBody.status).toBe("running");

    // 2e. Wait for approval.resolved, run.resumed, tool.started, tool.completed, run.completed
    const phase2Events = await waitForEvents(baseUrl, runId, (events) => {
      const types = events.map((e) => e.type);
      return (
        types.includes("approval.resolved") &&
        types.includes("run.resumed") &&
        types.includes("tool.completed") &&
        types.includes("run.completed")
      );
    });

    expect(phase2Events.some((e) => e.type === "approval.resolved")).toBe(true);
    expect(phase2Events.some((e) => e.type === "run.resumed")).toBe(true);
    expect(phase2Events.some((e) => e.type === "tool.started")).toBe(true);
    expect(phase2Events.some((e) => e.type === "tool.completed")).toBe(true);
    expect(phase2Events.some((e) => e.type === "run.completed")).toBe(true);

    // 2f. Verify run record shows completed
    const runBody = await fetchJson(`${baseUrl}/runs/${runId}`) as Record<string, unknown>;
    expect(runBody.status).toBe("completed");
  });

  // ── Test 3: Event sequence strictly increasing ───────────────────────────

  it("should have strictly increasing event sequences", { timeout: 15000 }, async () => {
    const runId = await createAndCompleteRun(baseUrl, "Test sequence.");

    const eventsBody = await fetchJson(`${baseUrl}/runs/${runId}/events`) as AgentStreamEvent[];
    const sequences = eventsBody.map((e) => e.sequence).sort((a, b) => a - b);
    const isIncreasing = sequences.every((s, i) => i === 0 || s > sequences[i - 1]!);
    expect(isIncreasing).toBe(true);
    expect(sequences.length).toBeGreaterThan(0);
  });

  // ── Test 4: Bad request ─────────────────────────────────────────────────

  it("should return 400 when creating run without goal", async () => {
    const body = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    }) as Record<string, unknown>;

    // Fetch doesn't throw on non-2xx, so we check the body
    expect(body).toHaveProperty("error");
    const error = (body as { error: { code: string } }).error;
    expect(error.code).toBe("BAD_REQUEST");
  });

  // ── Test 5: Thread creation and message append ──────────────────────────

  it("should create thread and append messages", async () => {
    const thread = await fetchJson(`${baseUrl}/threads`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "Test thread", orgId: "org_1", ownerUserId: "user_1" }),
    }) as Record<string, unknown>;

    expect(thread).toHaveProperty("id");
    expect(thread.title).toBe("Test thread");

    const threadId = thread.id as string;

    const msg = await fetchJson(`${baseUrl}/threads/${threadId}/messages`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ role: "user", content: "Hello" }),
    }) as Record<string, unknown>;

    expect(msg).toHaveProperty("id");
    expect(msg.content).toBe("Hello");

    const messages = await fetchJson(`${baseUrl}/threads/${threadId}/messages`) as unknown[];
    expect(messages).toHaveLength(1);
  });

  // ── Test 6: Event filtering with ?after= ────────────────────────────────

  it("should filter events with after query", async () => {
    const createBody = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ goal: "Test after query.", scopes: ["*"] }),
    }) as Record<string, unknown>;
    const runId = createBody.runId as string;

    // Wait for at least some events
    await waitForEvents(baseUrl, runId, (events) => events.length >= 3);

    const allEvents = await fetchJson(`${baseUrl}/runs/${runId}/events`) as AgentStreamEvent[];
    const after1 = await fetchJson(`${baseUrl}/runs/${runId}/events?after=1`) as AgentStreamEvent[];

    expect(after1.length).toBeLessThan(allEvents.length);
    expect(after1.every((e) => e.sequence > 1)).toBe(true);
  });

  // ── Test 7: Resume from /runs/:runId/resume ─────────────────────────────

  it("should resume run via POST /runs/:runId/resume", async () => {
    const createBody = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ goal: "Resume test.", scopes: ["*"] }),
    }) as Record<string, unknown>;
    const runId = createBody.runId as string;

    // Wait for pause
    await waitForEvents(baseUrl, runId, (events) =>
      events.some((e) => e.type === "run.paused"),
    );

    // Get approval
    const approvals = await fetchJson(`${baseUrl}/approvals?status=pending`) as unknown[];
    const approval = (approvals as Record<string, unknown>[]).find(
      (a) => a.runId === runId,
    ) as Record<string, unknown>;

    const resumeBody = await fetchJson(`${baseUrl}/runs/${runId}/resume`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        approvalId: approval.id,
        decision: "approved",
      }),
    }) as Record<string, unknown>;

    expect(resumeBody.runId).toBe(runId);
    expect(resumeBody.status).toBe("running");

    // Wait for completion
    await waitForEvents(baseUrl, runId, (events) =>
      events.some((e) => e.type === "run.completed"),
    );

    const run = await fetchJson(`${baseUrl}/runs/${runId}`) as Record<string, unknown>;
    expect(run.status).toBe("completed");
  });

  // ── Test 8: 404 for unknown run ─────────────────────────────────────────

  it("should return 404 for unknown run", async () => {
    const body = await fetchJson(`${baseUrl}/runs/run_nonexistent`) as Record<string, unknown>;
    expect(body).toHaveProperty("error");
    expect((body as { error: { code: string } }).error.code).toBe("NOT_FOUND");
  });

  // ── Test 9: Run metadata projection ─────────────────────────────────────

  it("should preserve run metadata in projection", async () => {
    const thread = await fetchJson(`${baseUrl}/threads`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "Metadata test", orgId: "org_test", ownerUserId: "user_test" }),
    }) as Record<string, unknown>;
    const threadId = thread.id as string;

    const createBody = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        goal: "Metadata projection test.",
        orgId: "org_test_42",
        actorUserId: "user_test_99",
        threadId,
        skillId: "skill_test_1",
        scopes: ["*"],
      }),
    }) as Record<string, unknown>;
    const runId = createBody.runId as string;

    const run = await fetchJson(`${baseUrl}/runs/${runId}`) as Record<string, unknown>;
    expect(run.goal).toBe("Metadata projection test.");
    expect(run.orgId).toBe("org_test_42");
    expect(run.actorUserId).toBe("user_test_99");
    expect(run.threadId).toBe(threadId);
    expect(run.skillId).toBe("skill_test_1");
  });

  // ── Test: External approvals not projected into Agent approvals ─────────

  it("should not project workflow-owned external approvals into Agent approvals", async () => {
    const rt = createAgentServerRuntime();
    projectEventIntoStore({
      id: "run_external:1" as any,
      runId: "run_external" as any,
      sequence: 1,
      timestamp: new Date().toISOString(),
      type: "run.created",
      source: { kind: "harness" },
      visibility: "user",
      redaction: "none",
      payload: { workspaceId: "ws_external", orgId: "org_1", actorUserId: "user_1", goal: "External" },
    }, rt.store);
    projectEventIntoStore({
      id: "run_external:2" as any,
      runId: "run_external" as any,
      sequence: 2,
      timestamp: new Date().toISOString(),
      type: "external_approval.requested",
      source: { kind: "external" },
      visibility: "user",
      redaction: "partial",
      payload: {
        kind: "workflow_capability",
        capabilityRunId: "caprun_1",
        approvalId: "capapproval_1",
      },
    }, rt.store);

    const approvals = await rt.store.listApprovals();
    expect(approvals).toEqual([]);
  });

  // ── Test 10: Cancel paused run ──────────────────────────────────────────

  it("should cancel paused run and expire pending approval", async () => {
    const createBody = await fetchJson(`${baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ goal: "Cancel test.", scopes: ["*"] }),
    }) as Record<string, unknown>;
    const runId = createBody.runId as string;

    // Wait for the run to pause
    await waitForEvents(baseUrl, runId, (events) =>
      events.some((e) => e.type === "run.paused"),
    );

    // Wait for projection to catch up (cancelRun reads from store, not event store)
    await waitForRunStatus(baseUrl, runId, "waiting_approval");

    // Get the pending approval
    const approvals = await fetchJson(`${baseUrl}/approvals?status=pending`) as unknown[];
    const approval = (approvals as Record<string, unknown>[]).find(
      (a) => a.runId === runId,
    ) as Record<string, unknown>;
    const approvalId = approval.id as string;

    // Cancel the run
    const cancelBody = await fetchJson(`${baseUrl}/runs/${runId}/cancel`, {
      method: "POST",
    }) as Record<string, unknown>;
    expect(cancelBody.status).toBe("cancel_requested");

    // Verify run status is cancelled
    const run = await fetchJson(`${baseUrl}/runs/${runId}`) as Record<string, unknown>;
    expect(run.status).toBe("cancelled");

    // Verify approval is expired with preserved metadata
    const expiredApproval = await fetchJson(`${baseUrl}/approvals/${approvalId}`) as Record<string, unknown>;
    expect(expiredApproval.status).toBe("expired");
    expect(expiredApproval.toolName).toBe("workspace.writeFile");

    // Verify events contain terminal and expiry events
    const events = await fetchJson(`${baseUrl}/runs/${runId}/events`) as AgentStreamEvent[];
    expect(events.some((e) => e.type === "run.cancelled")).toBe(true);
    expect(events.some((e) => e.type === "approval.expired")).toBe(true);
  });
});
