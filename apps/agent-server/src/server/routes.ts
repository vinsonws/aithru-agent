import type { IncomingMessage, ServerResponse } from "node:http";
import { formatSseEvent } from "@aithru/agent-stream";
import type { AgentStreamEvent } from "@aithru/agent-stream";
import type { RunId, ApprovalId } from "@aithru/agent-core";
import type { AgentServerRuntime } from "../runtime/create-agent-server-runtime.js";
import { sendJson, sendError, parseJsonBody } from "./json.js";
import { setupSse } from "./sse.js";
import { AgentServerError } from "./errors.js";
import type { AgentHttpContext } from "./context.js";
import { createStandaloneContext } from "./context.js";

// ── URL path parsing ───────────────────────────────────────────────────────

type ParsedPath = {
  parts: string[];
  query: URLSearchParams;
};

function parsePath(req: IncomingMessage): ParsedPath {
  const url = new URL(req.url ?? "/", "http://localhost");
  const parts = url.pathname.split("/").filter(Boolean);
  return { parts, query: url.searchParams };
}

// ── Route handler ──────────────────────────────────────────────────────────

export async function handleRequest(
  req: IncomingMessage,
  res: ServerResponse,
  rt: AgentServerRuntime,
  ctx: AgentHttpContext = createStandaloneContext(),
): Promise<void> {
  const method = req.method?.toUpperCase() ?? "GET";
  const { parts, query } = parsePath(req);

  try {
    await route(method, parts, query, req, res, rt, ctx);
  } catch (err) {
    if (err instanceof AgentServerError) {
      const status = err.code === "NOT_FOUND" ? 404
        : err.code === "BAD_REQUEST" ? 400
        : err.code === "RUN_NOT_RESUMABLE" ? 409
        : err.code === "APPROVAL_NOT_FOUND" ? 404
        : err.code === "AITHRU_AUTHZ_DENIED" ? 403
        : 500;
      sendError(res, status, err.code, err.message);
    } else if (err instanceof Error && err.message === "Invalid JSON body") {
      sendError(res, 400, "BAD_REQUEST", "Invalid JSON body");
    } else if (err instanceof Error && (
      err.name === "AithruAuthzDeniedError" ||
      err.message.startsWith("Missing required scope:")
    )) {
      sendError(res, 403, "AITHRU_AUTHZ_DENIED", err.message);
    } else {
      console.error("[agent-server] Unhandled error:", err);
      sendError(res, 500, "INTERNAL_ERROR", "Internal server error");
    }
  }
}

async function route(
  method: string,
  parts: string[],
  query: URLSearchParams,
  req: IncomingMessage,
  res: ServerResponse,
  rt: AgentServerRuntime,
  ctx: AgentHttpContext,
): Promise<void> {
  // GET /health (no auth required)
  if (method === "GET" && parts.length === 1 && parts[0] === "health") {
    return handleHealth(res);
  }

  // GET /me
  if (method === "GET" && parts.length === 1 && parts[0] === "me") {
    await ctx.requireScope("agent.app.view");
    return handleMe(res, ctx);
  }

  // ── Threads ─────────────────────────────────────────────────────────────

  // POST /threads
  if (method === "POST" && parts.length === 1 && parts[0] === "threads") {
    await ctx.requireScope("agent.thread.write");
    return handleCreateThread(req, res, rt, ctx);
  }

  // GET /threads
  if (method === "GET" && parts.length === 1 && parts[0] === "threads") {
    await ctx.requireScope("agent.thread.read");
    return handleListThreads(res, rt, ctx);
  }

  // GET /threads/:threadId
  if (method === "GET" && parts.length === 2 && parts[0] === "threads") {
    await ctx.requireScope("agent.thread.read");
    return handleGetThread(res, rt, parts[1]!, ctx);
  }

  // POST /threads/:threadId/messages
  if (method === "POST" && parts.length === 3 && parts[0] === "threads" && parts[2] === "messages") {
    await ctx.requireScope("agent.thread.write");
    return handleAppendMessage(req, res, rt, parts[1]!, ctx);
  }

  // GET /threads/:threadId/messages
  if (method === "GET" && parts.length === 3 && parts[0] === "threads" && parts[2] === "messages") {
    await ctx.requireScope("agent.thread.read");
    return handleListMessages(res, rt, parts[1]!, ctx);
  }

  // ── Runs ────────────────────────────────────────────────────────────────

  // POST /runs
  if (method === "POST" && parts.length === 1 && parts[0] === "runs") {
    await ctx.requireScope("agent.run.create");
    return handleCreateRun(req, res, rt, ctx);
  }

  // GET /runs
  if (method === "GET" && parts.length === 1 && parts[0] === "runs") {
    await ctx.requireScope("agent.run.read");
    return handleListRuns(res, rt, ctx);
  }

  // GET /runs/:runId
  if (method === "GET" && parts.length === 2 && parts[0] === "runs") {
    await ctx.requireScope("agent.run.read");
    return handleGetRun(res, rt, parts[1]!, ctx);
  }

  // GET /runs/:runId/events
  if (method === "GET" && parts.length === 3 && parts[0] === "runs" && parts[2] === "events") {
    await ctx.requireScope("agent.run.read");
    return handleGetRunEvents(res, rt, parts[1]!, query, ctx);
  }

  // GET /runs/:runId/stream
  if (method === "GET" && parts.length === 3 && parts[0] === "runs" && parts[2] === "stream") {
    await ctx.requireScope("agent.run.read");
    return handleRunSse(req, res, rt, parts[1]!, query, ctx);
  }

  // POST /runs/:runId/resume
  if (method === "POST" && parts.length === 3 && parts[0] === "runs" && parts[2] === "resume") {
    await ctx.requireScope("agent.approval.resolve");
    return handleResumeRun(req, res, rt, parts[1]!, ctx);
  }

  // POST /runs/:runId/cancel
  if (method === "POST" && parts.length === 3 && parts[0] === "runs" && parts[2] === "cancel") {
    await ctx.requireScope("agent.run.cancel");
    return handleCancelRun(res, rt, parts[1]!, ctx);
  }

  // ── Approvals ───────────────────────────────────────────────────────────

  // GET /approvals
  if (method === "GET" && parts.length === 1 && parts[0] === "approvals") {
    await ctx.requireScope("agent.approval.read");
    return handleListApprovals(res, rt, query, ctx);
  }

  // GET /approvals/:approvalId
  if (method === "GET" && parts.length === 2 && parts[0] === "approvals") {
    await ctx.requireScope("agent.approval.read");
    return handleGetApproval(res, rt, parts[1]!, ctx);
  }

  // POST /approvals/:approvalId/resolve
  if (method === "POST" && parts.length === 3 && parts[0] === "approvals" && parts[2] === "resolve") {
    await ctx.requireScope("agent.approval.resolve");
    return handleResolveApproval(req, res, rt, parts[1]!, ctx);
  }

  // ── 404 ─────────────────────────────────────────────────────────────────
  sendError(res, 404, "NOT_FOUND", `Route not found: ${req.method} ${req.url}`);
}

// ── Health ─────────────────────────────────────────────────────────────────

function handleHealth(res: ServerResponse): void {
  sendJson(res, 200, {
    ok: true,
    service: "agent-server",
    version: "0.2.0-alpha.0",
  });
}

// ── Me ─────────────────────────────────────────────────────────────────────

function handleMe(res: ServerResponse, ctx: AgentHttpContext): void {
  sendJson(res, 200, {
    mode: ctx.mode,
    actor: ctx.actor ?? null,
  });
}

// ── Thread handlers ────────────────────────────────────────────────────────

async function handleCreateThread(
  req: IncomingMessage,
  res: ServerResponse,
  rt: AgentServerRuntime,
  ctx: AgentHttpContext,
): Promise<void> {
  const body = (await parseJsonBody(req)) as Record<string, unknown> | undefined;

  const orgId =
    ctx.mode === "platform"
      ? (ctx.actor?.orgId ?? failClosed("orgId"))
      : ((body?.orgId as string) ?? "org_1");

  const ownerUserId =
    ctx.mode === "platform"
      ? (ctx.actor?.userId ?? failClosed("userId"))
      : ((body?.ownerUserId as string) ?? "user_1");

  const title = body?.title as string | undefined;

  const thread = await rt.store.createThread({
    orgId: orgId as any,
    ownerUserId: ownerUserId as any,
    title,
  });

  // Audit in platform mode
  if (ctx.auditSuccess) {
    await ctx.auditSuccess("agent.thread.create", {
      targetType: "thread",
      targetId: thread.id,
      metadata: { title: thread.title, orgId },
    }).catch((err) => warnBestEffortFailure("auditSuccess(agent.thread.create)", err));
  }

  sendJson(res, 201, thread);
}

async function handleListThreads(
  res: ServerResponse,
  rt: AgentServerRuntime,
  ctx: AgentHttpContext,
): Promise<void> {
  const threads = await rt.store.listThreads();
  sendJson(res, 200, filterByActorOrg(threads, ctx));
}

async function handleGetThread(
  res: ServerResponse,
  rt: AgentServerRuntime,
  threadId: string,
  ctx: AgentHttpContext,
): Promise<void> {
  const thread = await rt.store.getThread(threadId as any);
  if (!thread || !isActorOrgResource(thread, ctx)) {
    return sendError(res, 404, "NOT_FOUND", `Thread not found: ${threadId}`);
  }
  sendJson(res, 200, thread);
}

async function handleAppendMessage(
  req: IncomingMessage,
  res: ServerResponse,
  rt: AgentServerRuntime,
  threadId: string,
  ctx: AgentHttpContext,
): Promise<void> {
  const thread = await rt.store.getThread(threadId as any);
  if (!thread || !isActorOrgResource(thread, ctx)) {
    return sendError(res, 404, "NOT_FOUND", `Thread not found: ${threadId}`);
  }

  const body = (await parseJsonBody(req)) as Record<string, unknown> | undefined;
  const role = body?.role as string;
  const content = body?.content as string;

  if (!role || !content) {
    return sendError(res, 400, "BAD_REQUEST", "role and content are required");
  }

  const msg = await rt.store.appendMessage({
    threadId: threadId as any,
    role: role as any,
    content,
    runId: body?.runId as any,
  });
  sendJson(res, 201, msg);
}

async function handleListMessages(
  res: ServerResponse,
  rt: AgentServerRuntime,
  threadId: string,
  ctx: AgentHttpContext,
): Promise<void> {
  const thread = await rt.store.getThread(threadId as any);
  if (!thread || !isActorOrgResource(thread, ctx)) {
    return sendError(res, 404, "NOT_FOUND", `Thread not found: ${threadId}`);
  }
  const messages = await rt.store.listMessages(threadId as any);
  sendJson(res, 200, messages);
}

// ── Run handlers ───────────────────────────────────────────────────────────

async function handleCreateRun(
  req: IncomingMessage,
  res: ServerResponse,
  rt: AgentServerRuntime,
  ctx: AgentHttpContext,
): Promise<void> {
  const body = (await parseJsonBody(req)) as Record<string, unknown> | undefined;

  const goal = body?.goal as string | undefined;
  if (!goal || typeof goal !== "string" || goal.trim().length === 0) {
    return sendError(res, 400, "BAD_REQUEST", "goal is required and must be a non-empty string");
  }

  let orgId: string;
  let actorUserId: string;
  let scopes: string[] | undefined;

  if (ctx.mode === "platform") {
    // Platform mode: identity comes from token, never from body
    orgId = ctx.actor?.orgId ?? failClosed("orgId");
    actorUserId = ctx.actor?.userId ?? failClosed("userId");
    scopes = mapPlatformScopesToHarnessScopes(ctx.actor?.scopes ?? []);
  } else {
    orgId = (body?.orgId as string) ?? "org_1";
    actorUserId = (body?.actorUserId as string) ?? "user_1";
    scopes = body?.scopes as string[] | undefined;
  }

  const threadId = body?.threadId as string | undefined;
  const skillId = body?.skillId as string | undefined;

  const runId = await rt.runController.startRun({
    orgId: orgId as any,
    actorUserId: actorUserId as any,
    goal,
    threadId: threadId as any,
    skillId: skillId as any,
    scopes,
  });

  // Audit in platform mode
  if (ctx.auditSuccess) {
    await ctx.auditSuccess("agent.run.create", {
      targetType: "run",
      targetId: runId,
      metadata: { goal: goal.slice(0, 80), threadId: threadId ?? null, orgId },
    }).catch((err) => warnBestEffortFailure("auditSuccess(agent.run.create)", err));
  }

  sendJson(res, 201, {
    runId,
    status: "queued",
    threadId: threadId ?? null,
    eventsUrl: `${apiBasePath(ctx)}/runs/${runId}/events`,
    streamUrl: `${apiBasePath(ctx)}/runs/${runId}/stream`,
  });
}

async function handleListRuns(
  res: ServerResponse,
  rt: AgentServerRuntime,
  ctx: AgentHttpContext,
): Promise<void> {
  const runs = await rt.store.listRuns();
  sendJson(res, 200, filterByActorOrg(runs, ctx));
}

async function handleGetRun(
  res: ServerResponse,
  rt: AgentServerRuntime,
  runId: string,
  ctx: AgentHttpContext,
): Promise<void> {
  const run = await rt.store.getRun(runId as RunId);
  if (!run || !isActorOrgResource(run, ctx)) {
    return sendError(res, 404, "NOT_FOUND", `Run not found: ${runId}`);
  }
  sendJson(res, 200, run);
}

async function handleGetRunEvents(
  res: ServerResponse,
  rt: AgentServerRuntime,
  runId: string,
  query: URLSearchParams,
  ctx: AgentHttpContext,
): Promise<void> {
  const run = await rt.store.getRun(runId as RunId);
  if (!run || !isActorOrgResource(run, ctx)) {
    return sendError(res, 404, "NOT_FOUND", `Run not found: ${runId}`);
  }

  const afterStr = query.get("after");
  const after = afterStr ? parseInt(afterStr, 10) : undefined;

  const events = after !== undefined && !isNaN(after)
    ? await rt.eventStore.listAfterSequence(runId as RunId, after)
    : await rt.eventStore.listByRun(runId as RunId);

  sendJson(res, 200, events);
}

async function handleRunSse(
  req: IncomingMessage,
  res: ServerResponse,
  rt: AgentServerRuntime,
  runId: string,
  query: URLSearchParams,
  ctx: AgentHttpContext,
): Promise<void> {
  const run = await rt.store.getRun(runId as RunId);
  if (!run || !isActorOrgResource(run, ctx)) {
    return sendError(res, 404, "NOT_FOUND", `Run not found: ${runId}`);
  }

  const afterStr = query.get("after");
  const after = afterStr ? parseInt(afterStr, 10) : 0;

  // Send historical events first
  const history = after > 0
    ? await rt.eventStore.listAfterSequence(runId as RunId, after)
    : await rt.eventStore.listByRun(runId as RunId);

  const sse = setupSse(res);

  for (const event of history) {
    sse.write(formatSseEvent(event));
  }

  // Subscribe to real-time events
  const subscriber = (event: AgentStreamEvent) => {
    sse.write(formatSseEvent(event));
  };
  rt.eventBus.subscribe(runId as RunId, subscriber);

  req.on("close", () => {
    rt.eventBus.unsubscribe(runId as RunId, subscriber);
    sse.close();
  });
}

async function handleResumeRun(
  req: IncomingMessage,
  res: ServerResponse,
  rt: AgentServerRuntime,
  runId: string,
  ctx: AgentHttpContext,
): Promise<void> {
  const body = (await parseJsonBody(req)) as Record<string, unknown> | undefined;

  const approvalId = body?.approvalId as string | undefined;
  const decision = body?.decision as string | undefined;

  if (!approvalId) {
    return sendError(res, 400, "BAD_REQUEST", "approvalId is required");
  }

  if (decision !== "approved" && decision !== "rejected") {
    return sendError(res, 400, "BAD_REQUEST", "decision must be 'approved' or 'rejected'");
  }

  const run = await rt.store.getRun(runId as RunId);
  if (!run || !isActorOrgResource(run, ctx)) {
    return sendError(res, 404, "NOT_FOUND", `Run not found: ${runId}`);
  }

  if (!rt.runController.hasRun(runId as RunId)) {
    return sendError(res, 409, "RUN_NOT_RESUMABLE", `Run ${runId} is not resumable (already completed or engine not available)`);
  }

  const approval = await rt.store.getApproval(approvalId as ApprovalId);
  if (!approval) {
    return sendError(res, 404, "APPROVAL_NOT_FOUND", `Approval not found: ${approvalId}`);
  }
  if (!(await isApprovalVisibleToActorOrg(rt, approval.runId, ctx))) {
    return sendError(res, 404, "APPROVAL_NOT_FOUND", `Approval not found: ${approvalId}`);
  }

  if (approval.runId !== (runId as RunId)) {
    return sendError(res, 400, "BAD_REQUEST", "Approval does not belong to this run");
  }

  const comment = body?.comment as string | undefined;

  await rt.runController.resumeRunWithProjection(runId as RunId, {
    approvalId: approvalId as ApprovalId,
    decision: decision as "approved" | "rejected",
    comment,
  });

  // Audit in platform mode
  if (ctx.auditSuccess) {
    await ctx.auditSuccess("agent.approval.resolve", {
      targetType: "approval",
      targetId: approvalId,
      metadata: {
        runId,
        decision,
      },
    }).catch((err) => warnBestEffortFailure("auditSuccess(agent.approval.resolve)", err));
  }

  sendJson(res, 200, {
    runId,
    approvalId,
    status: "running",
  });
}

async function handleCancelRun(
  res: ServerResponse,
  rt: AgentServerRuntime,
  runId: string,
  ctx: AgentHttpContext,
): Promise<void> {
  const run = await rt.store.getRun(runId as RunId);
  if (!run || !isActorOrgResource(run, ctx)) {
    return sendError(res, 404, "NOT_FOUND", `Run not found: ${runId}`);
  }

  try {
    await rt.runController.cancelRun(runId as RunId);

    // Audit in platform mode
    if (ctx.auditSuccess) {
      await ctx.auditSuccess("agent.run.cancel", {
        targetType: "run",
        targetId: runId,
        metadata: { orgId: run.orgId },
      }).catch((err) => warnBestEffortFailure("auditSuccess(agent.run.cancel)", err));
    }

    sendJson(res, 200, {
      runId,
      status: "cancel_requested",
    });
  } catch (err) {
    // Audit failure in platform mode
    if (ctx.auditFailure) {
      await ctx.auditFailure("agent.run.cancel", {
        targetType: "run",
        targetId: runId,
        error: err,
      }).catch((auditErr) => warnBestEffortFailure("auditFailure(agent.run.cancel)", auditErr));
    }
    throw err;
  }
}

// ── Approval handlers ──────────────────────────────────────────────────────

async function handleListApprovals(
  res: ServerResponse,
  rt: AgentServerRuntime,
  query: URLSearchParams,
  ctx: AgentHttpContext,
): Promise<void> {
  const status = query.get("status") as any ?? undefined;
  const runId = query.get("runId") as any ?? undefined;

  const approvals = await rt.store.listApprovals({ status, runId });
  if (ctx.mode !== "platform") {
    sendJson(res, 200, approvals);
    return;
  }

  const runs = await rt.store.listRuns();
  const visibleRunIds = new Set(filterByActorOrg(runs, ctx).map((run) => run.id));
  sendJson(res, 200, approvals.filter((approval) => visibleRunIds.has(approval.runId)));
}

async function handleGetApproval(
  res: ServerResponse,
  rt: AgentServerRuntime,
  approvalId: string,
  ctx: AgentHttpContext,
): Promise<void> {
  const approval = await rt.store.getApproval(approvalId as ApprovalId);
  if (!approval) {
    return sendError(res, 404, "NOT_FOUND", `Approval not found: ${approvalId}`);
  }
  if (!(await isApprovalVisibleToActorOrg(rt, approval.runId, ctx))) {
    return sendError(res, 404, "NOT_FOUND", `Approval not found: ${approvalId}`);
  }
  sendJson(res, 200, approval);
}

async function handleResolveApproval(
  req: IncomingMessage,
  res: ServerResponse,
  rt: AgentServerRuntime,
  approvalId: string,
  ctx: AgentHttpContext,
): Promise<void> {
  const body = (await parseJsonBody(req)) as Record<string, unknown> | undefined;
  const decision = body?.decision as string | undefined;
  const comment = body?.comment as string | undefined;

  if (decision !== "approved" && decision !== "rejected") {
    return sendError(res, 400, "BAD_REQUEST", "decision must be 'approved' or 'rejected'");
  }

  const approval = await rt.store.getApproval(approvalId as ApprovalId);
  if (!approval) {
    return sendError(res, 404, "APPROVAL_NOT_FOUND", `Approval not found: ${approvalId}`);
  }
  if (!(await isApprovalVisibleToActorOrg(rt, approval.runId, ctx))) {
    return sendError(res, 404, "APPROVAL_NOT_FOUND", `Approval not found: ${approvalId}`);
  }

  if (!rt.runController.hasRun(approval.runId)) {
    return sendError(res, 409, "RUN_NOT_RESUMABLE", `Run ${approval.runId} is not resumable`);
  }

  await rt.runController.resumeRunWithProjection(approval.runId, {
    approvalId: approvalId as ApprovalId,
    decision: decision as "approved" | "rejected",
    comment,
  });

  // Audit in platform mode
  if (ctx.auditSuccess) {
    await ctx.auditSuccess("agent.approval.resolve", {
      targetType: "approval",
      targetId: approvalId,
      metadata: {
        runId: approval.runId,
        decision,
      },
    }).catch((err) => warnBestEffortFailure("auditSuccess(agent.approval.resolve)", err));
  }

  sendJson(res, 200, {
    approvalId,
    decision,
    status: "running",
  });
}

// ── Helpers ────────────────────────────────────────────────────────────────

function failClosed(field: string): never {
  throw new AgentServerError(
    "AITHRU_AUTHZ_DENIED",
    `Missing required actor field: ${field}`,
  );
}

function apiBasePath(ctx: AgentHttpContext): string {
  if (ctx.apiBasePath !== undefined) return ctx.apiBasePath;
  return ctx.mode === "platform" ? "/api/agent" : "";
}

function isActorOrgResource<T extends { orgId?: unknown }>(
  record: T,
  ctx: AgentHttpContext,
): boolean {
  if (ctx.mode !== "platform") return true;
  const actorOrgId = ctx.actor?.orgId ?? failClosed("orgId");
  return record.orgId === actorOrgId;
}

function filterByActorOrg<T extends { orgId?: unknown }>(
  records: T[],
  ctx: AgentHttpContext,
): T[] {
  if (ctx.mode !== "platform") return records;
  const actorOrgId = ctx.actor?.orgId ?? failClosed("orgId");
  return records.filter((record) => record.orgId === actorOrgId);
}

async function isApprovalVisibleToActorOrg(
  rt: AgentServerRuntime,
  runId: RunId,
  ctx: AgentHttpContext,
): Promise<boolean> {
  if (ctx.mode !== "platform") return true;
  const run = await rt.store.getRun(runId);
  return Boolean(run && isActorOrgResource(run, ctx));
}

function mapPlatformScopesToHarnessScopes(platformScopes: string[]): string[] {
  const mapped = new Set<string>();

  for (const scope of platformScopes) {
    switch (scope) {
      case "*":
        mapped.add("*");
        break;
      case "agent.workspace.read":
        mapped.add("workspace:read");
        break;
      case "agent.workspace.write":
        mapped.add("workspace:write");
        break;
      case "agent.search.read":
        mapped.add("search:read");
        break;
      case "agent.fetch.read":
        mapped.add("fetch:read");
        break;
    }
  }

  return [...mapped];
}

function warnBestEffortFailure(operation: string, err: unknown): void {
  const message = err instanceof Error ? err.message : String(err);
  console.warn(`[agent-server] ${operation} failed: ${message}`);
}
