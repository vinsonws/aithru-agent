import type { IncomingMessage, ServerResponse } from "node:http";
import { formatSseEvent } from "@aithru/agent-stream";
import type { AgentStreamEvent } from "@aithru/agent-stream";
import type { RunId, ApprovalId } from "@aithru/agent-core";
import type { AgentServerRuntime } from "../runtime/create-agent-server-runtime.js";
import { sendJson, sendError, parseJsonBody } from "./json.js";
import { setupSse } from "./sse.js";
import { AgentServerError } from "./errors.js";

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
): Promise<void> {
  const method = req.method?.toUpperCase() ?? "GET";
  const { parts, query } = parsePath(req);

  try {
    await route(method, parts, query, req, res, rt);
  } catch (err) {
    if (err instanceof AgentServerError) {
      const status = err.code === "NOT_FOUND" ? 404
        : err.code === "BAD_REQUEST" ? 400
        : err.code === "RUN_NOT_RESUMABLE" ? 409
        : err.code === "APPROVAL_NOT_FOUND" ? 404
        : 500;
      sendError(res, status, err.code, err.message);
    } else if (err instanceof Error && err.message === "Invalid JSON body") {
      sendError(res, 400, "BAD_REQUEST", "Invalid JSON body");
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
): Promise<void> {
  // GET /health
  if (method === "GET" && parts.length === 1 && parts[0] === "health") {
    return handleHealth(res);
  }

  // ── Threads ─────────────────────────────────────────────────────────────

  // POST /threads
  if (method === "POST" && parts.length === 1 && parts[0] === "threads") {
    return handleCreateThread(req, res, rt);
  }

  // GET /threads
  if (method === "GET" && parts.length === 1 && parts[0] === "threads") {
    return handleListThreads(res, rt);
  }

  // GET /threads/:threadId
  if (method === "GET" && parts.length === 2 && parts[0] === "threads") {
    return handleGetThread(res, rt, parts[1]!);
  }

  // POST /threads/:threadId/messages
  if (method === "POST" && parts.length === 3 && parts[0] === "threads" && parts[2] === "messages") {
    return handleAppendMessage(req, res, rt, parts[1]!);
  }

  // GET /threads/:threadId/messages
  if (method === "GET" && parts.length === 3 && parts[0] === "threads" && parts[2] === "messages") {
    return handleListMessages(res, rt, parts[1]!);
  }

  // ── Runs ────────────────────────────────────────────────────────────────

  // POST /runs
  if (method === "POST" && parts.length === 1 && parts[0] === "runs") {
    return handleCreateRun(req, res, rt);
  }

  // GET /runs
  if (method === "GET" && parts.length === 1 && parts[0] === "runs") {
    return handleListRuns(res, rt);
  }

  // GET /runs/:runId
  if (method === "GET" && parts.length === 2 && parts[0] === "runs") {
    return handleGetRun(res, rt, parts[1]!);
  }

  // GET /runs/:runId/events
  if (method === "GET" && parts.length === 3 && parts[0] === "runs" && parts[2] === "events") {
    return handleGetRunEvents(res, rt, parts[1]!, query);
  }

  // GET /runs/:runId/stream
  if (method === "GET" && parts.length === 3 && parts[0] === "runs" && parts[2] === "stream") {
    return handleRunSse(req, res, rt, parts[1]!, query);
  }

  // POST /runs/:runId/resume
  if (method === "POST" && parts.length === 3 && parts[0] === "runs" && parts[2] === "resume") {
    return handleResumeRun(req, res, rt, parts[1]!);
  }

  // POST /runs/:runId/cancel
  if (method === "POST" && parts.length === 3 && parts[0] === "runs" && parts[2] === "cancel") {
    return handleCancelRun(res, rt, parts[1]!);
  }

  // ── Approvals ───────────────────────────────────────────────────────────

  // GET /approvals
  if (method === "GET" && parts.length === 1 && parts[0] === "approvals") {
    return handleListApprovals(res, rt, query);
  }

  // GET /approvals/:approvalId
  if (method === "GET" && parts.length === 2 && parts[0] === "approvals") {
    return handleGetApproval(res, rt, parts[1]!);
  }

  // POST /approvals/:approvalId/resolve
  if (method === "POST" && parts.length === 3 && parts[0] === "approvals" && parts[2] === "resolve") {
    return handleResolveApproval(req, res, rt, parts[1]!);
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

// ── Thread handlers ────────────────────────────────────────────────────────

async function handleCreateThread(req: IncomingMessage, res: ServerResponse, rt: AgentServerRuntime): Promise<void> {
  const body = (await parseJsonBody(req)) as Record<string, unknown> | undefined;
  const orgId = (body?.orgId as string) ?? "org_1";
  const ownerUserId = (body?.ownerUserId as string) ?? "user_1";
  const title = body?.title as string | undefined;

  const thread = await rt.store.createThread({
    orgId: orgId as any,
    ownerUserId: ownerUserId as any,
    title,
  });
  sendJson(res, 201, thread);
}

function handleListThreads(res: ServerResponse, rt: AgentServerRuntime): Promise<void> {
  return rt.store.listThreads().then((threads) => sendJson(res, 200, threads));
}

async function handleGetThread(res: ServerResponse, rt: AgentServerRuntime, threadId: string): Promise<void> {
  const thread = await rt.store.getThread(threadId as any);
  if (!thread) {
    return sendError(res, 404, "NOT_FOUND", `Thread not found: ${threadId}`);
  }
  sendJson(res, 200, thread);
}

async function handleAppendMessage(req: IncomingMessage, res: ServerResponse, rt: AgentServerRuntime, threadId: string): Promise<void> {
  const thread = await rt.store.getThread(threadId as any);
  if (!thread) {
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

async function handleListMessages(res: ServerResponse, rt: AgentServerRuntime, threadId: string): Promise<void> {
  const thread = await rt.store.getThread(threadId as any);
  if (!thread) {
    return sendError(res, 404, "NOT_FOUND", `Thread not found: ${threadId}`);
  }
  const messages = await rt.store.listMessages(threadId as any);
  sendJson(res, 200, messages);
}

// ── Run handlers ───────────────────────────────────────────────────────────

async function handleCreateRun(req: IncomingMessage, res: ServerResponse, rt: AgentServerRuntime): Promise<void> {
  const body = (await parseJsonBody(req)) as Record<string, unknown> | undefined;

  const goal = body?.goal as string | undefined;
  if (!goal || typeof goal !== "string" || goal.trim().length === 0) {
    return sendError(res, 400, "BAD_REQUEST", "goal is required and must be a non-empty string");
  }

  const orgId = (body?.orgId as string) ?? "org_1";
  const actorUserId = (body?.actorUserId as string) ?? "user_1";
  const threadId = body?.threadId as string | undefined;
  const skillId = body?.skillId as string | undefined;
  const scopes = body?.scopes as string[] | undefined;

  const runId = await rt.runController.startRun({
    orgId: orgId as any,
    actorUserId: actorUserId as any,
    goal,
    threadId: threadId as any,
    skillId: skillId as any,
    scopes,
  });

  sendJson(res, 201, {
    runId,
    status: "queued",
    threadId: threadId ?? null,
    eventsUrl: `/runs/${runId}/events`,
    streamUrl: `/runs/${runId}/stream`,
  });
}

async function handleListRuns(res: ServerResponse, rt: AgentServerRuntime): Promise<void> {
  const runs = await rt.store.listRuns();
  sendJson(res, 200, runs);
}

async function handleGetRun(res: ServerResponse, rt: AgentServerRuntime, runId: string): Promise<void> {
  const run = await rt.store.getRun(runId as RunId);
  if (!run) {
    return sendError(res, 404, "NOT_FOUND", `Run not found: ${runId}`);
  }
  sendJson(res, 200, run);
}

async function handleGetRunEvents(
  res: ServerResponse,
  rt: AgentServerRuntime,
  runId: string,
  query: URLSearchParams,
): Promise<void> {
  const run = await rt.store.getRun(runId as RunId);
  if (!run) {
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
): Promise<void> {
  const run = await rt.store.getRun(runId as RunId);
  if (!run) {
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

async function handleResumeRun(req: IncomingMessage, res: ServerResponse, rt: AgentServerRuntime, runId: string): Promise<void> {
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
  if (!run) {
    return sendError(res, 404, "NOT_FOUND", `Run not found: ${runId}`);
  }

  if (!rt.runController.hasRun(runId as RunId)) {
    return sendError(res, 409, "RUN_NOT_RESUMABLE", `Run ${runId} is not resumable (already completed or engine not available)`);
  }

  const approval = await rt.store.getApproval(approvalId as ApprovalId);
  if (!approval) {
    return sendError(res, 404, "APPROVAL_NOT_FOUND", `Approval not found: ${approvalId}`);
  }

  if (approval.runId !== (runId as RunId)) {
    return sendError(res, 400, "BAD_REQUEST", "Approval does not belong to this run");
  }

  const comment = body?.comment as string | undefined;

  await rt.runController.resumeRun(runId as RunId, {
    approvalId: approvalId as ApprovalId,
    decision: decision as "approved" | "rejected",
    comment,
  });

  sendJson(res, 200, {
    runId,
    approvalId,
    status: "running",
  });
}

async function handleCancelRun(res: ServerResponse, rt: AgentServerRuntime, runId: string): Promise<void> {
  const run = await rt.store.getRun(runId as RunId);
  if (!run) {
    return sendError(res, 404, "NOT_FOUND", `Run not found: ${runId}`);
  }

  await rt.runController.cancelRun(runId as RunId);

  sendJson(res, 200, {
    runId,
    status: "cancel_requested",
  });
}

// ── Approval handlers ──────────────────────────────────────────────────────

async function handleListApprovals(res: ServerResponse, rt: AgentServerRuntime, query: URLSearchParams): Promise<void> {
  const status = query.get("status") as any ?? undefined;
  const runId = query.get("runId") as any ?? undefined;

  const approvals = await rt.store.listApprovals({ status, runId });
  sendJson(res, 200, approvals);
}

async function handleGetApproval(res: ServerResponse, rt: AgentServerRuntime, approvalId: string): Promise<void> {
  const approval = await rt.store.getApproval(approvalId as ApprovalId);
  if (!approval) {
    return sendError(res, 404, "NOT_FOUND", `Approval not found: ${approvalId}`);
  }
  sendJson(res, 200, approval);
}

async function handleResolveApproval(req: IncomingMessage, res: ServerResponse, rt: AgentServerRuntime, approvalId: string): Promise<void> {
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

  if (!rt.runController.hasRun(approval.runId)) {
    return sendError(res, 409, "RUN_NOT_RESUMABLE", `Run ${approval.runId} is not resumable`);
  }

  await rt.runController.resumeRun(approval.runId, {
    approvalId: approvalId as ApprovalId,
    decision: decision as "approved" | "rejected",
    comment,
  });

  // Update the projection
  await rt.store.resolveApproval(approvalId as ApprovalId, decision as "approved" | "rejected", comment);

  sendJson(res, 200, {
    approvalId,
    decision,
    status: "running",
  });
}
