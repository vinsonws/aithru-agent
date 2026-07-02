import { createHash } from "node:crypto";
import { join } from "node:path";
import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { nanoid } from "nanoid";
import type { AgentMessage, AgentRun, AgentThread } from "@aithru-agent/contracts";
import { emitSkillActivated, ensureToolCallRecordForApproval, getToolCallRecord } from "@aithru-agent/harness";
import { EVENT_TYPES } from "@aithru-agent/stream";
import { projectTraceSpans } from "@aithru-agent/trace";
import { projectCapabilityAudit } from "@aithru-agent/capabilities";
import {
  buildRunSnapshot,
  buildRunTree,
  buildRunTreeUsage,
  buildRunUsageSummary,
} from "@aithru-agent/snapshots";
import { SkillLoader, findBuiltinSkillsRoot, type SkillPackage } from "@aithru-agent/skills";
import { getRuntime } from "../runtime.js";
import type { AgentToolDescriptor } from "@aithru-agent/capabilities";
import { shouldFollowRunStream, writeRunStream } from "./run-stream.js";
import {
  actorCanAccessOwnedResource,
  bodyWithPlatformActor,
  platformActorFromRequest,
  requestActorUserId,
  requestOrgId as platformRequestOrgId,
} from "../platform-auth.js";

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function params(request: FastifyRequest): Record<string, string> {
  return request.params as Record<string, string>;
}

function query(request: FastifyRequest): Record<string, string | undefined> {
  return (request.query ?? {}) as Record<string, string | undefined>;
}

function notFound(reply: FastifyReply, message: string) {
  reply.code(404);
  return { error: message };
}

function forbidden(reply: FastifyReply) {
  reply.code(403);
  return { error: "Forbidden" };
}

function accessibleThread(
  request: FastifyRequest,
  reply: FastifyReply,
  threadId: string,
): { thread: AgentThread; response?: never } | { thread?: never; response: { error: string } } {
  const thread = getRuntime().store.getThread(threadId);
  if (!thread) return { response: notFound(reply, "Thread not found") };
  if (!actorCanAccessOwnedResource(platformActorFromRequest(request), thread)) return { response: forbidden(reply) };
  return { thread };
}

function accessibleRun(
  request: FastifyRequest,
  reply: FastifyReply,
  runId: string,
  threadId?: string,
): { run: AgentRun; response?: never } | { run?: never; response: { error: string } } {
  const run = getRuntime().store.getRun(runId);
  if (!run || (threadId && run.thread_id !== threadId)) return { response: notFound(reply, "Run not found") };
  if (!actorCanAccessOwnedResource(platformActorFromRequest(request), run)) return { response: forbidden(reply) };
  return { run };
}

function workspaceIdForThread(threadId: string | null): string {
  return threadId ? `ws_thread_${threadId}` : `ws_${nanoid(12)}`;
}

function afterSequence(request: FastifyRequest): number {
  const raw = query(request).after_sequence;
  const value = typeof raw === "string" ? Number(raw) : 0;
  return Number.isFinite(value) && value > 0 ? value : 0;
}

class SelectedSkillNotFoundError extends Error {
  constructor(readonly key: string) {
    super(`Skill not found: ${key}`);
  }
}

class ResourceForbiddenError extends Error {}

class ThreadNotFoundError extends Error {}

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

async function createRun(
  inputBody: any,
  threadId?: string,
  actor: ReturnType<typeof platformActorFromRequest> = null,
): Promise<AgentRun> {
  const body = bodyWithPlatformActor(inputBody, actor);
  const runtime = getRuntime();
  const orgId = body.org_id ?? "org_1";
  const actorUserId = body.actor_user_id ?? "user_1";
  const runThreadId =
    threadId ?? (typeof body.thread_id === "string" && body.thread_id.length > 0 ? body.thread_id : null);
  if (runThreadId && actor) {
    const thread = runtime.store.getThread(runThreadId);
    if (!thread) throw new ThreadNotFoundError();
    if (!actorCanAccessOwnedResource(actor, thread)) throw new ResourceForbiddenError();
  }
  const selectedSkills = [];
  for (const key of selectedSkillKeys(body)) {
    const skill = runtime.skillResolver.resolve(key, orgId, actorUserId);
    if (!skill) throw new SelectedSkillNotFoundError(key);
    selectedSkills.push(skill);
  }
  const run: AgentRun = {
    id: `run_${nanoid(12)}`,
    org_id: orgId,
    actor_user_id: actorUserId,
    source: body.source ?? "chat",
    thread_id: runThreadId,
    workspace_id: workspaceIdForThread(runThreadId),
    task_msg: body.task_msg ?? "",
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
  if (body.persist_task_msg_message === true && runThreadId && runtime.store.getThread(runThreadId)) {
    const message: AgentMessage = {
      id: `msg_${nanoid(12)}`,
      thread_id: runThreadId,
      role: "user",
      content: run.task_msg,
      run_id: run.id,
      workspace_paths: [],
      created_at: now(),
    };
    runtime.store.createMessage(message);
    runtime.store.updateThread(runThreadId, { updated_at: now() });
  }
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
  if (body.wait_for_completion === true) {
    return (await runtime.scheduleRunExecution(run, { wait: true })) ?? run;
  }
  void runtime.scheduleRunExecution(run);
  return run;
}

function cancelRun(runId: string, request: FastifyRequest, reply: FastifyReply) {
  const runtime = getRuntime();
  const run = runtime.store.getRun(runId);
  if (!run) return notFound(reply, "Run not found");
  if (!actorCanAccessOwnedResource(platformActorFromRequest(request), run)) return forbidden(reply);
  return runtime.cancelRun(runId, run.org_id) ?? notFound(reply, "Run not found");
}

async function submitRunInput(
  runId: string,
  request: FastifyRequest,
  reply: FastifyReply,
) {
  const runtime = getRuntime();
  const run = runtime.store.getRun(runId);
  if (!run) return notFound(reply, "Run not found");
  if (!actorCanAccessOwnedResource(platformActorFromRequest(request), run)) return forbidden(reply);
  if (["completed", "failed", "cancelled"].includes(String(run.status))) {
    reply.code(409);
    return { error: "Run is not accepting input" };
  }
  if (!run.thread_id) {
    reply.code(409);
    return { error: "Run has no thread" };
  }

  const body = (request.body ?? {}) as {
    content?: unknown;
    response?: unknown;
    input_request_id?: unknown;
  };
  const content =
    typeof body.response === "string"
      ? body.response.trim()
      : typeof body.content === "string"
        ? body.content.trim()
        : "";
  if (!content) {
    reply.code(400);
    return { error: "response is required" };
  }
  const providedInputRequestId =
    typeof body.input_request_id === "string" && body.input_request_id.trim()
      ? body.input_request_id.trim()
      : null;

  let inputRequestId: string | null = null;
  let toolCallId: string | null = null;
  let toolRecord: ReturnType<typeof getToolCallRecord> | null = null;
  if (run.status === "waiting_input") {
    const events = runtime.store.listEvents(run.id);
    const inputRequest = [...events]
      .reverse()
      .find((event) => event.type === EVENT_TYPES.INPUT_REQUESTED);
    inputRequestId =
      inputRequest && typeof (inputRequest.payload as any)?.input_request_id === "string"
        ? (inputRequest.payload as any).input_request_id
        : null;
    toolCallId =
      inputRequest && typeof (inputRequest.payload as any)?.tool_call_id === "string"
        ? (inputRequest.payload as any).tool_call_id
        : null;
    if (providedInputRequestId && providedInputRequestId !== inputRequestId) {
      reply.code(400);
      return { error: "input_request_id does not match the active request" };
    }
    if (
      inputRequestId &&
      events.some((event) =>
        event.type === EVENT_TYPES.INPUT_RECEIVED &&
        (event.payload as any)?.input_request_id === inputRequestId,
      )
    ) {
      reply.code(400);
      return { error: "input_request_id was already submitted" };
    }
    toolRecord = toolCallId ? getToolCallRecord(runtime.store, toolCallId) : null;
    if (providedInputRequestId && !toolRecord) {
      reply.code(400);
      return { error: "input_request_id has no matching tool call" };
    }
  } else if (providedInputRequestId) {
    reply.code(400);
    return { error: "input_request_id is not active" };
  }

  const message: AgentMessage = {
    id: `msg_${nanoid(12)}`,
    thread_id: run.thread_id,
    role: "user",
    content,
    run_id: run.id,
    workspace_paths: [],
    created_at: now(),
  };
  runtime.store.createMessage(message);
  runtime.store.updateThread(run.thread_id, { updated_at: now() });
  runtime.eventWriter.write(
    run.id,
    run.thread_id,
    EVENT_TYPES.MESSAGE_CREATED,
    { message_id: message.id, role: "user" },
    { source: { kind: "user", id: run.actor_user_id } },
  );
  runtime.eventWriter.write(
    run.id,
    run.thread_id,
    EVENT_TYPES.MESSAGE_COMPLETED,
    { message_id: message.id, content },
    { source: { kind: "user", id: run.actor_user_id } },
  );

  if (run.status !== "waiting_input") return run;

  runtime.eventWriter.write(
    run.id,
    run.thread_id,
    EVENT_TYPES.INPUT_RECEIVED,
    {
      input_request_id: inputRequestId,
      message_id: message.id,
      content,
      response: content,
      tool_call_id: toolCallId,
    },
    { source: { kind: "user", id: run.actor_user_id } },
  );
  const updated = runtime.store.updateRun(run.id, { status: "queued" });
  runtime.eventWriter.write(
    run.id,
    run.thread_id,
    EVENT_TYPES.RUN_RESUMED,
    { status: "queued", resume_reason: "input_received" },
  );
  void runtime.scheduleRunExecution(updated, {
    toolResults: toolRecord
      ? [{
          id: toolRecord.id,
          name: toolRecord.tool_name,
          input: toolRecord.input,
          output: { input_request_id: inputRequestId, response: content },
        }]
      : [],
  });
  return updated;
}

async function sendRunStream(
  runId: string,
  request: FastifyRequest,
  reply: FastifyReply,
  minSequence = 0,
  threadId?: string,
) {
  const runtime = getRuntime();
  const access = accessibleRun(request, reply, runId, threadId);
  if (access.response) return access.response;
  const run = access.run;
  void runtime.scheduleRunExecution(run);
  return writeRunStream({
    request,
    reply,
    runtime,
    runId,
    minSequence,
    follow: shouldFollowRunStream(request.query),
  });
}

async function createRunStream(
  body: any,
  request: FastifyRequest,
  reply: FastifyReply,
  threadId?: string,
) {
  let run: AgentRun;
  try {
    run = await createRun(body, threadId, platformActorFromRequest(request));
  } catch (error) {
    if (error instanceof SelectedSkillNotFoundError) {
      reply.code(400);
      return { error: error.message };
    }
    if (error instanceof ThreadNotFoundError) return notFound(reply, "Thread not found");
    if (error instanceof ResourceForbiddenError) return forbidden(reply);
    throw error;
  }
  return writeRunStream({
    request,
    reply,
    runtime: getRuntime(),
    runId: run.id,
    minSequence: 0,
    follow: true,
  });
}

async function createRunResponse(
  body: any,
  reply: FastifyReply,
  threadId?: string,
  request?: FastifyRequest,
) {
  try {
    return await createRun(body, threadId, request ? platformActorFromRequest(request) : null);
  } catch (error) {
    if (error instanceof SelectedSkillNotFoundError) {
      reply.code(400);
      return { error: error.message };
    }
    if (error instanceof ThreadNotFoundError) return notFound(reply, "Thread not found");
    if (error instanceof ResourceForbiddenError) return forbidden(reply);
    throw error;
  }
}

function runUsage(runId: string) {
  return buildRunUsageSummary(getRuntime().store, runId);
}

function treeUsage(runId: string) {
  return buildRunTreeUsage(getRuntime().store, runId);
}

function runInspection(runId: string) {
  const runtime = getRuntime();
  const run = runtime.store.getRun(runId);
  if (!run) return undefined;
  const events = runtime.store.listEvents(runId);
  const todos = runtime.store.listTodos(runId);
  const approvals = runtime.store.listApprovals({ run_id: runId });
  const files = runtime.store.listWorkspaceFiles(run.workspace_id);
  return {
    health: run.status,
    needs_attention: ["waiting_approval", "waiting_input", "waiting_external_run", "failed"].includes(String(run.status)),
    attention_reasons: [],
    event_count: events.length,
    todo_count: todos.length,
    blocked_todo_count: todos.filter((todo) => todo.status === "blocked").length,
    workspace_file_count: files.length,
    approval_count: approvals.length,
    failed_trace_count: events.filter((event) => event.type.endsWith(".failed")).length,
    research_status: "none",
    research_degraded: false,
    last_event_type: events.at(-1)?.type ?? null,
    external_runs: [],
    external_run_count: 0,
    failed_external_run_count: 0,
    cancelled_external_run_count: 0,
    active_external_run: null,
    external_run_stale: false,
    sandbox_runs: [],
    sandbox_run_count: 0,
    failed_sandbox_run_count: 0,
    sandbox_workspace_file_count: 0,
    sandbox_persistence_error_count: 0,
    sandbox_operator_actions: [],
    sandbox_operator_action_count: 0,
  };
}

function threadSummary(threadId: string, actor: ReturnType<typeof platformActorFromRequest> = null) {
  const runtime = getRuntime();
  const thread = runtime.store.getThread(threadId);
  const messages = runtime.store.listMessages(threadId, thread?.org_id);
  const runs = runtime.store
    .listRuns({ thread_id: threadId })
    .filter((run) => actorCanAccessOwnedResource(actor, run));
  const latestMessage = messages.at(-1);
  const latestRun = runs.at(-1);
  const activeRunCount = runs.filter((run) => ["queued", "running"].includes(String(run.status))).length;
  return {
    thread_id: threadId,
    message_count: messages.length,
    run_count: runs.length,
    active_run_count: activeRunCount,
    waiting_input_run_count: runs.filter((run) => run.status === "waiting_input").length,
    latest_message: latestMessage
      ? {
          message_id: latestMessage.id,
          role: latestMessage.role,
          content_preview: latestMessage.content.slice(0, 160),
          truncated: latestMessage.content.length > 160,
          created_at: latestMessage.created_at,
          run_id: latestMessage.run_id ?? null,
          workspace_paths: latestMessage.workspace_paths,
        }
      : null,
    latest_run: latestRun
      ? {
          run_id: latestRun.id,
          status: latestRun.status,
          task_msg: latestRun.task_msg,
          started_at: latestRun.started_at,
          completed_at: latestRun.completed_at ?? null,
        }
      : null,
    last_activity_at: latestRun?.started_at ?? latestMessage?.created_at ?? null,
  };
}

function workbenchRun(run: AgentRun) {
  return {
    run,
    summary: runInspection(run.id),
    action_hints: [],
    action_count: 0,
    high_priority_action_count: 0,
  };
}

function dashboardItem(thread: any, actor: ReturnType<typeof platformActorFromRequest> = null) {
  const runtime = getRuntime();
  const runs = runtime.store
    .listRuns({ thread_id: thread.id })
    .filter((run) => actorCanAccessOwnedResource(actor, run));
  const latestRun = runs.at(-1);
  const summary = threadSummary(thread.id, actor);
  return {
    thread,
    summary,
    latest_run: latestRun ? workbenchRun(latestRun) : null,
    needs_attention: false,
    attention_reasons: [],
    research_status: "none",
    research_degraded: false,
    last_activity_at: summary.last_activity_at ?? thread.updated_at ?? thread.created_at,
    action_hints: [],
    action_count: 0,
    high_priority_action_count: 0,
  };
}

function timestampMillis(value: unknown): number {
  const millis = typeof value === "string" ? Date.parse(value) : NaN;
  return Number.isFinite(millis) ? millis : 0;
}

function approvalResponse(approval: any) {
  const resolved = approval.status === "approved" || approval.status === "denied";
  const toolCall = ensureToolCallRecordForApproval(getRuntime().store, approval);
  return {
    ...approval,
    tool_input: toolCall?.input ?? null,
    status: resolved ? "resolved" : approval.status,
    decision:
      approval.status === "approved"
        ? "approved"
        : approval.status === "denied"
          ? "rejected"
          : null,
    comment: null,
    metadata: null,
  };
}

function workspaceFile(file: any) {
  return {
    workspace_id: file.workspace_id,
    path: file.path,
    size: file.size,
    media_type: workspaceMediaTypeForPath(file.path),
    version: file.version,
    file_version: file.version,
    content_hash: null,
    created_by_run_id: file.created_by_run_id ?? null,
    last_modified_by_run_id: file.last_modified_by_run_id ?? null,
    created_at: file.created_at,
    updated_at: file.updated_at,
  };
}

function workspaceMediaTypeForPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "html" || ext === "htm") return "text/html";
  if (ext === "md" || ext === "markdown") return "text/markdown";
  if (ext === "json") return "application/json";
  if (ext === "css") return "text/css";
  if (ext === "js" || ext === "mjs") return "text/javascript";
  if (ext === "csv") return "text/csv";
  if (ext === "svg") return "image/svg+xml";
  if (ext === "png") return "image/png";
  if (ext === "jpg" || ext === "jpeg") return "image/jpeg";
  if (ext === "gif") return "image/gif";
  if (ext === "webp") return "image/webp";
  if (ext === "pdf") return "application/pdf";
  return "text/plain";
}

function workspaceContentTypeForPath(path: string): string {
  const mediaType = workspaceMediaTypeForPath(path);
  return mediaType.startsWith("text/") || mediaType === "application/json"
    ? `${mediaType}; charset=utf-8`
    : mediaType;
}

const workspaceFileSuffixActions = ["content", "download", "versions", "patch", "convert", "promote"] as const;
type WorkspaceFileSuffixAction = (typeof workspaceFileSuffixActions)[number];
type WorkspaceFileWildcardAction = WorkspaceFileSuffixAction | "read";

function isWorkspaceFileSuffixAction(value: string | undefined): value is WorkspaceFileSuffixAction {
  return typeof value === "string" && (workspaceFileSuffixActions as readonly string[]).includes(value);
}

function decodeWorkspacePathSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function workspaceFileWildcardTarget(request: FastifyRequest): {
  workspaceId: string;
  path: string;
  action: WorkspaceFileWildcardAction;
} | undefined {
  const raw = params(request)["*"];
  if (!raw) return undefined;
  const segments = raw.split("/").filter(Boolean).map(decodeWorkspacePathSegment);
  const suffix = segments.at(-1);
  const action: WorkspaceFileWildcardAction = isWorkspaceFileSuffixAction(suffix) ? suffix : "read";
  const pathSegments = action === "read" ? segments : segments.slice(0, -1);
  if (pathSegments.length === 0) return undefined;
  return {
    workspaceId: params(request).workspace_id,
    path: `/${pathSegments.join("/")}`,
    action,
  };
}

function applyWorkspaceFilePatch(request: FastifyRequest, reply: FastifyReply, workspaceId: string, path: string) {
  const runtime = getRuntime();
  const file = runtime.store.readFile(workspaceId, path);
  if (!file) return notFound(reply, "Workspace file not found");
  const before = file.version;
  let content = file.content;
  let replacements = 0;
  for (const edit of ((request.body as any)?.edits ?? [])) {
    const search = String(edit.search ?? edit.old_text ?? "");
    const replace = String(edit.replace ?? edit.new_text ?? "");
    if (!search || !content.includes(search)) continue;
    content = edit.replace_all ? content.split(search).join(replace) : content.replace(search, replace);
    replacements += 1;
  }
  const updated = runtime.store.writeFile(workspaceId, path, content);
  return {
    workspace_id: updated.workspace_id,
    path: updated.path,
    version_before: before,
    version_after: updated.version,
    file_version_before: before,
    file_version_after: updated.version,
    size_before: file.size,
    size_after: updated.size,
    replacement_count: replacements,
    content_hash: null,
  };
}

function workspaceFileWildcardRequest(request: FastifyRequest, reply: FastifyReply) {
  const target = workspaceFileWildcardTarget(request);
  if (!target) return notFound(reply, "Workspace file not found");
  const runtime = getRuntime();

  if (request.method === "GET") {
    const file = runtime.store.readFile(target.workspaceId, target.path);
    if (!file) return notFound(reply, "Workspace file not found");
    if (target.action === "content") {
      reply.header("content-type", workspaceContentTypeForPath(file.path));
      return file.content;
    }
    if (target.action === "download") {
      reply.header("content-type", "application/octet-stream");
      return file.content;
    }
    if (target.action === "versions") {
      return [{
        ...workspaceFile(file),
        operation: "write",
        created_at: file.created_at,
      }];
    }
    if (target.action === "read") return { path: file.path, content: file.content, media_type: workspaceMediaTypeForPath(file.path) };
  }

  if (request.method === "PUT" && target.action === "read") {
    const body = (request.body ?? {}) as any;
    const file = runtime.store.writeFile(target.workspaceId, target.path, String(body.content ?? ""));
    return workspaceFile(file);
  }

  if (request.method === "DELETE" && target.action === "read") {
    runtime.store.deleteFile(target.workspaceId, target.path);
    return { path: target.path };
  }

  if (request.method === "POST") {
    if (target.action === "patch") return applyWorkspaceFilePatch(request, reply, target.workspaceId, target.path);
    if (target.action === "convert") {
      const file = runtime.store.readFile(target.workspaceId, target.path);
      if (!file) return notFound(reply, "Workspace file not found");
      return {
        workspace_id: file.workspace_id,
        source_path: file.path,
        source_media_type: workspaceMediaTypeForPath(file.path),
        source_size: file.size,
        output_file: null,
        skipped: true,
      };
    }
    if (target.action === "promote") {
      return {
        workspace_id: target.workspaceId,
        path: target.path,
        promoted: false,
      };
    }
  }

  return notFound(reply, "Workspace file not found");
}

function workspaceSnapshot(workspaceId: string) {
  const runtime = getRuntime();
  const files = runtime.store.listWorkspaceFiles(workspaceId).map(workspaceFile);
  return {
    workspace_id: workspaceId,
    version: 1,
    files,
    file_count: files.length,
    total_size: files.reduce((sum, file) => sum + file.size, 0),
    created_at: now(),
  };
}

function defaultModelProfile(key = "default") {
  const timestamp = now();
  return {
    org_id: "org_1",
    key,
    name: key === "default" ? "Default" : key,
    provider: "test",
    model: "test",
    enabled: true,
    capabilities: { vision: false, thinking: false },
    cost_policy: null,
    selection_policy: { required_scopes: [], max_total_tokens: null },
    auth_secret: { has_secret: false, secret_ref: null, redacted: true },
    metadata: null,
    id: `model_profile_${key}`,
    created_at: timestamp,
    updated_at: timestamp,
  };
}

function requestOrgId(request: FastifyRequest, body?: any): string {
  return platformRequestOrgId(platformActorFromRequest(request), body, query(request));
}

function requestOwnerUserId(request: FastifyRequest, body?: any): string {
  return requestActorUserId(platformActorFromRequest(request), body);
}

function documentWriteGuard(request: FastifyRequest, body?: any) {
  const actor = platformActorFromRequest(request);
  return {
    orgId: requestOrgId(request, body),
    ...(actor ? { ownerUserId: requestOwnerUserId(request, body) } : {}),
  };
}

function canAccessDocument(request: FastifyRequest, payload: any): boolean {
  return actorCanAccessOwnedResource(platformActorFromRequest(request), payload);
}

function documentPayload<T>(kind: string, id: string): T | null {
  return (getRuntime().store.getDocument(kind, id)?.payload as T | undefined) ?? null;
}

function listDocumentPayloads<T>(kind: string, orgId: string): T[] {
  return getRuntime().store.listDocuments(kind, orgId).map((doc) => doc.payload as T);
}

function modelProfileId(orgId: string, key: string): string {
  const digest = createHash("sha256").update(`${orgId}\0${key}`).digest("hex").slice(0, 20);
  return `model_profile_${digest}`;
}

function modelProfileSecretRef(orgId: string, key: string): string {
  return `secret://model-profiles/${orgId}/${key}/api-key`;
}

function secretStatus(secretRef: string | null = null) {
  return secretRef
    ? { has_secret: true, secret_ref: secretRef, redacted: true }
    : { has_secret: false, secret_ref: null, redacted: true };
}

function resolveModelProfileSecret(input: any, orgId: string, key: string) {
  if (!input) return null;
  if (input.write_only_value != null) {
    if (typeof input.write_only_value !== "string" || !input.write_only_value.trim()) {
      throw new Error("write_only_value must be a nonblank string");
    }
    const ref = modelProfileSecretRef(orgId, key);
    getRuntime().store.setSecret(orgId, ref, input.write_only_value);
    return secretStatus(ref);
  }
  if (typeof input.secret_ref === "string" && input.secret_ref.trim()) {
    return secretStatus(input.secret_ref.trim());
  }
  return secretStatus();
}

function deleteMemoryResponse(request: FastifyRequest) {
  const memoryId = params(request).memory_id;
  const orgId = requestOrgId(request);
  const entry = documentPayload<any>("memory", memoryId);
  const deleted = entry?.org_id === orgId && canAccessDocument(request, entry)
    ? getRuntime().store.deleteDocument("memory", memoryId, documentWriteGuard(request))
    : 0;
  return {
    memory_id: memoryId,
    org_id: orgId,
    forgotten: deleted > 0,
    deleted_count: deleted,
  };
}

function createModelProfileFromBody(request: FastifyRequest, body: any) {
  const orgId = requestOrgId(request, body);
  const ownerUserId = requestOwnerUserId(request, body);
  const key = String(body.key ?? "custom");
  const timestamp = now();
  const profile = {
    ...defaultModelProfile(key),
    ...body,
    org_id: orgId,
    owner_user_id: ownerUserId,
    key,
    id: modelProfileId(orgId, key),
    enabled: body.enabled ?? true,
    auth_secret: resolveModelProfileSecret(body.auth_secret, orgId, key) ?? secretStatus(),
    created_at: timestamp,
    updated_at: timestamp,
  };
  delete (profile as any).auth_secret?.write_only_value;
  return profile;
}

function modelProfileByIdOrKey(orgId: string, value: string) {
  const byId = documentPayload<any>("model_profile_entry", value);
  if (byId?.org_id === orgId) return byId;
  return listDocumentPayloads<any>("model_profile_entry", orgId).find(
    (profile) => profile.key === value,
  ) ?? null;
}

function accessibleModelProfileByIdOrKey(request: FastifyRequest, value: string) {
  const profile = modelProfileByIdOrKey(requestOrgId(request), value);
  return profile && canAccessDocument(request, profile) ? profile : null;
}

type BuiltinSkill = {
  key: string;
  name: string;
  description: string | null;
  instructions: string;
  allowed_tools: string[];
};

const FALLBACK_BUILTIN_SKILLS: BuiltinSkill[] = [
  {
    key: "general-agent",
    name: "General Agent",
    description: "General harness skill for chat, workspace, todo, and presentation work.",
    instructions: "Use the Agent Harness capability router for all real actions.",
    allowed_tools: [
      "workspace.list_files",
      "workspace.read_file",
      "workspace.write_file",
      "workspace.patch_file",
      "workspace.delete_file",
      "todo.create",
      "todo.update",
      "presentation.present",
    ],
  },
  {
    key: "file-report",
    name: "File Report",
    description: "Read workspace files and produce a report workspace file.",
    instructions: "Read relevant workspace files, write a report, and present the resulting resource.",
    allowed_tools: [
      "workspace.list_files",
      "workspace.read_file",
      "workspace.write_file",
      "todo.create",
      "todo.update",
      "presentation.present",
    ],
  },
];

let cachedBuiltinSkills: BuiltinSkill[] | null = null;

function skillFromPackage(pkg: SkillPackage): BuiltinSkill {
  return {
    key: pkg.key,
    name: pkg.name,
    description: pkg.description,
    instructions: pkg.instructions,
    allowed_tools: pkg.allowed_tools,
  };
}

function builtinSkills(): BuiltinSkill[] {
  if (cachedBuiltinSkills) return cachedBuiltinSkills;

  const root = findBuiltinSkillsRoot();
  if (!root) {
    cachedBuiltinSkills = FALLBACK_BUILTIN_SKILLS;
    return cachedBuiltinSkills;
  }

  const loader = new SkillLoader();
  const loaded = loader.loadBuiltinPackages(root)
    .map(skillFromPackage)
    .sort((a, b) => a.key.localeCompare(b.key));

  cachedBuiltinSkills = loaded.length > 0 ? loaded : FALLBACK_BUILTIN_SKILLS;
  return cachedBuiltinSkills;
}

function builtinSkill(key: string) {
  return builtinSkills().find((skill) => skill.key === key);
}

function skillEntry(key = "placeholder", enabled = true) {
  const builtin = builtinSkill(key);
  const timestamp = now();
  return {
    id: `skill_${key}`,
    org_id: "org_1",
    key,
    name: builtin?.name ?? key,
    description: builtin?.description ?? null,
    version: "0.0.0",
    status: "published",
    enabled,
    source: builtin ? "builtin" : "user",
    owner_user_id: null,
    marketplace: null,
    configuration: {
      instructions: builtin?.instructions ?? "",
      when_to_use: null,
      allowed_tools: [...(builtin?.allowed_tools ?? [])],
      denied_tools: [],
      allowed_subagents: [],
      workspace_policy: null,
      memory_policy: null,
      sandbox_policy: null,
      approval_policy: null,
      input_schema: null,
      output_schema: null,
    },
    read_only: Boolean(builtin),
    created_at: timestamp,
    updated_at: timestamp,
  };
}

function skillPackage(key = "placeholder", enabled = true) {
  const entry = skillEntry(key, enabled);
  return {
    id: entry.id,
    org_id: entry.org_id,
    key: entry.key,
    name: entry.name,
    description: entry.description,
    instructions: entry.configuration.instructions,
    when_to_use: entry.configuration.when_to_use,
    enabled: entry.enabled,
    allowed_tools: entry.configuration.allowed_tools,
    denied_tools: entry.configuration.denied_tools,
    allowed_subagents: entry.configuration.allowed_subagents,
    workspace_policy: null,
    memory_policy: null,
    sandbox_policy: null,
    approval_policy: null,
    input_schema: null,
    output_schema: null,
    version: entry.version,
    status: entry.status,
  };
}

function skillPackageFromEntry(entry: any) {
  return {
    id: entry.id,
    org_id: entry.org_id,
    key: entry.key,
    name: entry.name,
    description: entry.description,
    instructions: entry.configuration?.instructions ?? "",
    when_to_use: entry.configuration?.when_to_use ?? null,
    enabled: entry.enabled,
    allowed_tools: entry.configuration?.allowed_tools ?? [],
    denied_tools: entry.configuration?.denied_tools ?? [],
    allowed_subagents: entry.configuration?.allowed_subagents ?? [],
    workspace_policy: entry.configuration?.workspace_policy ?? null,
    memory_policy: entry.configuration?.memory_policy ?? null,
    sandbox_policy: entry.configuration?.sandbox_policy ?? null,
    approval_policy: entry.configuration?.approval_policy ?? null,
    input_schema: entry.configuration?.input_schema ?? null,
    output_schema: entry.configuration?.output_schema ?? null,
    version: entry.version,
    status: entry.status,
  };
}

function skillRegistryEntryForRequest(request: FastifyRequest, key: string) {
  return storedSkillRegistryEntry(requestOrgId(request), key, requestOwnerUserId(request)) ?? skillEntry(key);
}

function storedSkillRegistryEntry(orgId: string, key: string, ownerUserId?: string) {
  const byId = documentPayload<any>("skill_registry_entry", key);
  if (byId?.org_id === orgId && (!ownerUserId || byId.owner_user_id === ownerUserId)) return byId;
  return listDocumentPayloads<any>("skill_registry_entry", orgId).find(
    (entry) => entry.key === key && (!ownerUserId || entry.owner_user_id === ownerUserId),
  ) ?? null;
}

function skillRegistryEntries(request: FastifyRequest) {
  const orgId = requestOrgId(request);
  const stored = new Map(
    listDocumentPayloads<any>("skill_registry_entry", orgId)
      .filter((entry) => canAccessDocument(request, entry))
      .map((entry) => [entry.key, entry]),
  );
  for (const skill of builtinSkills()) {
    if (!stored.has(skill.key)) stored.set(skill.key, skillEntry(skill.key));
  }
  return [...stored.values()].sort((a, b) => String(a.key).localeCompare(String(b.key)));
}

function saveSkillRegistryEntry(request: FastifyRequest, reply: FastifyReply, key: string, patch: Record<string, unknown>) {
  const orgId = requestOrgId(request);
  const ownerUserId = requestOwnerUserId(request);
  const stored = storedSkillRegistryEntry(orgId, key, ownerUserId);
  const foreign = stored ? null : storedSkillRegistryEntry(orgId, key);
  if (foreign && !builtinSkill(key)) return forbidden(reply);
  const existing = stored ?? skillEntry(key);
  const updated = {
    ...existing,
    ...patch,
    org_id: orgId,
    owner_user_id: ownerUserId,
    key: existing.key,
    id: existing.id,
    updated_at: now(),
  };
  getRuntime().store.upsertDocument("skill_registry_entry", updated.id, updated, documentWriteGuard(request));
  return updated;
}

function toolCatalogEntry(tool: AgentToolDescriptor) {
  return {
    name: tool.name,
    description: tool.description,
    input_schema: tool.input_schema,
    output_schema: {},
    risk_level:
      tool.risk_level === "low"
        ? "read"
        : tool.risk_level === "medium"
          ? "write"
          : "dangerous",
    required_scopes: tool.required_scopes,
    approval_policy: tool.requires_approval ? "on_risk" : "never",
    failure_policy: "fail_run",
    metadata: null,
  };
}

async function localToolCatalog() {
  const run: AgentRun = {
    id: "run_tool_catalog",
    org_id: "org_1",
    actor_user_id: "system",
    source: "api",
    thread_id: null,
    workspace_id: "ws_tool_catalog",
    task_msg: "List tools",
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
  return (await getRuntime().capabilityRouter.listTools({ run })).map(toolCatalogEntry);
}

function externalToolConfig(key = "local-capabilities", enabled = true, tools: any[] = []) {
  const timestamp = now();
  return {
    id: `external_tool_${key}`,
    org_id: "org_1",
    key,
    provider_kind: "mcp",
    name: key === "local-capabilities" ? "Local Capabilities" : key,
    description: null,
    enabled,
    mcp: {
      server_key: key,
      name: "Local Capabilities",
      endpoint: {
        url: "local://capability-router",
        allowed_hosts: [],
        timeout_ms: 0,
        max_response_bytes: 0,
        auth_secret: { has_secret: false, secret_ref: null, redacted: true },
      },
      tools,
    },
    http: null,
    web: null,
    activation_status: "configured",
    oauth_status: { status: "not_configured", connected: false, last_error: null },
    cache_status: { status: "primed", updated_at: timestamp },
    created_at: timestamp,
    updated_at: timestamp,
    created_by: "system",
    updated_by: "system",
    audit: [],
  };
}

function externalToolConfigId(orgId: string, key: string): string {
  return `external_tool_config_${orgId}_${key}`;
}

function externalToolSecretRef(orgId: string, key: string): string {
  return `secret://external-tools/${orgId}/${key}/api-key`;
}

function resolveExternalSecret(input: any, orgId: string, key: string) {
  if (!input) return input;
  if (input.write_only_value != null) {
    if (typeof input.write_only_value !== "string" || !input.write_only_value.trim()) {
      throw new Error("write_only_value must be a nonblank string");
    }
    const ref = externalToolSecretRef(orgId, key);
    getRuntime().store.setSecret(orgId, ref, input.write_only_value);
    return secretStatus(ref);
  }
  if (typeof input.secret_ref === "string" && input.secret_ref.trim()) {
    return secretStatus(input.secret_ref.trim());
  }
  return secretStatus();
}

function resolveExternalToolSecrets(config: any, orgId: string, key: string) {
  const clone = structuredClone(config);
  for (const endpoint of [
    clone.mcp?.endpoint,
    clone.http?.endpoint,
    clone.web?.search_endpoint,
  ]) {
    if (endpoint?.auth_secret) {
      endpoint.auth_secret = resolveExternalSecret(endpoint.auth_secret, orgId, key);
    }
  }
  return clone;
}

function externalToolConfigFromBody(request: FastifyRequest, body: any) {
  const orgId = requestOrgId(request, body);
  const ownerUserId = requestOwnerUserId(request, body);
  const key = String(body.key ?? "custom");
  const timestamp = now();
  return resolveExternalToolSecrets({
    ...externalToolConfig(key, body.enabled ?? true),
    ...body,
    id: externalToolConfigId(orgId, key),
    org_id: orgId,
    owner_user_id: ownerUserId,
    key,
    enabled: body.enabled ?? true,
    activation_status: "pending_runtime_reload",
    created_at: timestamp,
    updated_at: timestamp,
    created_by: ownerUserId,
    updated_by: ownerUserId,
    audit: [
      {
        id: `audit_${nanoid(8)}`,
        action: "created",
        at: timestamp,
        actor_user_id: ownerUserId,
      },
    ],
  }, orgId, key);
}

function externalToolByIdOrKey(orgId: string, value: string) {
  const byId = documentPayload<any>("external_tool_config_entry", value);
  if (byId?.org_id === orgId) return byId;
  return listDocumentPayloads<any>("external_tool_config_entry", orgId).find(
    (config) => config.key === value,
  ) ?? null;
}

function accessibleExternalToolByIdOrKey(request: FastifyRequest, value: string) {
  const config = externalToolByIdOrKey(requestOrgId(request), value);
  return config && canAccessDocument(request, config) ? config : null;
}

function externalToolOperation(key: string, action: string, enabled: boolean) {
  const config = externalToolConfig(key, enabled);
  return {
    action,
    config,
    audit_event: {
      id: `audit_${nanoid(8)}`,
      action,
      at: now(),
      actor_user_id: "system",
    },
  };
}

function runExport(
  runId: string,
  request: FastifyRequest,
  reply: FastifyReply,
  threadId?: string,
) {
  const runtime = getRuntime();
  const access = accessibleRun(request, reply, runId, threadId);
  if (access.response) return access.response;
  const run = access.run;
  return {
    schema_version: "run_export.v1",
    exported_at: now(),
    run,
    events: runtime.store.listEvents(runId),
    trace: projectTraceSpans(runtime.store.listEvents(runId)),
    todos: runtime.store.listTodos(runId),
    approvals: runtime.store.listApprovals({ run_id: runId }).map(approvalResponse),
    workspace_snapshot: workspaceSnapshot(run.workspace_id),
    summary: {
      run_id: run.id,
      workspace_id: run.workspace_id,
      status: run.status,
      event_count: runtime.store.listEvents(runId).length,
    },
  };
}

function register(app: FastifyInstance, method: string, url: string, handler: any) {
  app.route({ method: method as any, url, handler });
}

export function registerCompatRoutes(app: FastifyInstance): void {
  register(app, "GET", "/api/threads/dashboard", async (request: FastifyRequest) => {
    const { status, limit = "20", offset = "0" } = query(request);
    const runtime = getRuntime();
    const actor = platformActorFromRequest(request);
    let threads = runtime.store
      .listThreads(actor?.orgId ?? query(request).org_id)
      .filter((thread) => actorCanAccessOwnedResource(actor, thread));
    if (status) threads = threads.filter((thread) => thread.status === status);
    const items = threads
      .map((thread) => dashboardItem(thread, actor))
      .sort((a, b) => timestampMillis(b.last_activity_at) - timestampMillis(a.last_activity_at));
    const page = items.slice(Number(offset), Number(offset) + Number(limit));
    return {
      items: page,
      total: threads.length,
      count: page.length,
      limit: Number(limit),
      offset: Number(offset),
      order_by: "last_activity_at",
      order_direction: "desc",
      status_counts: {
        active: threads.filter((thread) => thread.status === "active").length,
        archived: threads.filter((thread) => thread.status === "archived").length,
      },
      needs_attention_count: 0,
      research_degraded_count: 0,
      action_hint_count: 0,
      high_priority_action_hint_count: 0,
    };
  });

  register(app, "GET", "/api/threads/:thread_id", async (request: FastifyRequest, reply: FastifyReply) => {
    const access = accessibleThread(request, reply, params(request).thread_id);
    return access.response ?? access.thread;
  });
  register(app, "GET", "/api/threads/:thread_id/summary", async (request: FastifyRequest, reply: FastifyReply) => {
    const threadId = params(request).thread_id;
    const access = accessibleThread(request, reply, threadId);
    if (access.response) return access.response;
    return threadSummary(threadId, platformActorFromRequest(request));
  });
  register(app, "GET", "/api/threads/:thread_id/workbench", async (request: FastifyRequest, reply: FastifyReply) => {
    const threadId = params(request).thread_id;
    const access = accessibleThread(request, reply, threadId);
    if (access.response) return access.response;
    const actor = platformActorFromRequest(request);
    const runs = getRuntime().store
      .listRuns({ thread_id: threadId })
      .filter((run) => actorCanAccessOwnedResource(actor, run));
    const selectedRunId = query(request).selected_run_id ?? runs.at(-1)?.id ?? null;
    return {
      thread: access.thread,
      summary: threadSummary(threadId, actor),
      runs: runs.map(workbenchRun),
      selected_run_id: selectedRunId,
      selected_run: selectedRunId && runs.some((run) => run.id === selectedRunId)
        ? buildRunSnapshot(getRuntime().store, selectedRunId) ?? null
        : null,
    };
  });
  register(app, "GET", "/api/threads/:thread_id/runs", async (request: FastifyRequest, reply: FastifyReply) => {
    const threadId = params(request).thread_id;
    const access = accessibleThread(request, reply, threadId);
    if (access.response) return access.response;
    const actor = platformActorFromRequest(request);
    return getRuntime().store
      .listRuns({ thread_id: threadId })
      .filter((run) => actorCanAccessOwnedResource(actor, run));
  });
  register(app, "POST", "/api/threads/:thread_id/runs", async (request: FastifyRequest, reply: FastifyReply) =>
    createRunResponse(request.body ?? {}, reply, params(request).thread_id, request),
  );
  register(app, "POST", "/api/threads/:thread_id/runs/stream", async (request: FastifyRequest, reply: FastifyReply) =>
    createRunStream(request.body ?? {}, request, reply, params(request).thread_id),
  );

  register(app, "POST", "/api/runs/stream", async (request: FastifyRequest, reply: FastifyReply) =>
    createRunStream(request.body ?? {}, request, reply),
  );
  register(app, "POST", "/api/runs/wait", async (request: FastifyRequest, reply: FastifyReply) =>
    createRunResponse({ ...(request.body as any), wait_for_completion: true }, reply, undefined, request),
  );

  const runDetail = async (request: FastifyRequest, reply: FastifyReply) => {
    const access = accessibleRun(request, reply, params(request).run_id, params(request).thread_id);
    return access.response ?? access.run;
  };
  register(app, "GET", "/api/threads/:thread_id/runs/:run_id", runDetail);

  const runStream = async (request: FastifyRequest, reply: FastifyReply) =>
    sendRunStream(params(request).run_id, request, reply, afterSequence(request), params(request).thread_id);
  register(app, "GET", "/api/threads/:thread_id/runs/:run_id/stream", runStream);

  const runEvents = async (request: FastifyRequest, reply: FastifyReply) => {
    const runId = params(request).run_id;
    const access = accessibleRun(request, reply, runId, params(request).thread_id);
    if (access.response) return access.response;
    return getRuntime().store.listEvents(runId);
  };
  register(app, "GET", "/api/threads/:thread_id/runs/:run_id/events", runEvents);

  register(app, "GET", "/api/threads/:thread_id/runs/:run_id/capability-audit", async (request: FastifyRequest, reply: FastifyReply) => {
    const runId = params(request).run_id;
    const access = accessibleRun(request, reply, runId, params(request).thread_id);
    if (access.response) return access.response;
    return projectCapabilityAudit(getRuntime().store.listEvents(runId));
  });

  const runSummaryHandler = async (request: FastifyRequest, reply: FastifyReply) => {
    const access = accessibleRun(request, reply, params(request).run_id, params(request).thread_id);
    if (access.response) return access.response;
    return runInspection(access.run.id);
  };
  for (const path of [
    "/api/runs/:run_id/summary",
    "/api/threads/:thread_id/runs/:run_id/summary",
  ]) register(app, "GET", path, runSummaryHandler);

  const runUsageHandler = async (request: FastifyRequest, reply: FastifyReply) => {
    const runId = params(request).run_id;
    const access = accessibleRun(request, reply, runId, params(request).thread_id);
    if (access.response) return access.response;
    return runUsage(runId);
  };
  for (const path of [
    "/api/runs/:run_id/usage",
    "/api/threads/:thread_id/runs/:run_id/usage",
  ]) register(app, "GET", path, runUsageHandler);

  const treeHandler = async (request: FastifyRequest, reply: FastifyReply) => {
    const runId = params(request).run_id;
    const access = accessibleRun(request, reply, runId, params(request).thread_id);
    if (access.response) return access.response;
    return buildRunTree(getRuntime().store, runId) ?? notFound(reply, "Run not found");
  };
  register(app, "GET", "/api/runs/:run_id/tree", treeHandler);
  register(app, "GET", "/api/threads/:thread_id/runs/:run_id/tree", treeHandler);

  const treeUsageHandler = async (request: FastifyRequest, reply: FastifyReply) => {
    const runId = params(request).run_id;
    const access = accessibleRun(request, reply, runId, params(request).thread_id);
    if (access.response) return access.response;
    return treeUsage(runId);
  };
  register(app, "GET", "/api/runs/:run_id/tree/usage", treeUsageHandler);
  register(app, "GET", "/api/threads/:thread_id/runs/:run_id/tree/usage", treeUsageHandler);

  const memoryRecall = async (request: FastifyRequest, reply: FastifyReply) => {
    const runId = params(request).run_id;
    const access = accessibleRun(request, reply, runId, params(request).thread_id);
    if (access.response) return access.response;
    return { run_id: runId, items: [] };
  };
  register(app, "GET", "/api/runs/:run_id/memory-recall", memoryRecall);
  register(app, "GET", "/api/threads/:thread_id/runs/:run_id/memory-recall", memoryRecall);

  register(app, "GET", "/api/runs/:run_id/tools", async (request: FastifyRequest, reply: FastifyReply) => {
    const access = accessibleRun(request, reply, params(request).run_id);
    if (access.response) return access.response;
    const run = access.run;
    const tools = await getRuntime().capabilityRouter.listTools({ run });
    return tools.map((tool) => ({
      ...tool,
      kind: "local_tool",
      output_schema: {},
      risk_level:
        tool.risk_level === "low"
          ? "read"
          : tool.risk_level === "medium"
            ? "write"
            : "dangerous",
      approval_policy: tool.requires_approval ? "on_risk" : "never",
      failure_policy: "fail_run",
    }));
  });
  register(app, "GET", "/api/runs/:run_id/subagents", async (request: FastifyRequest, reply: FastifyReply) => {
    const runId = params(request).run_id;
    const access = accessibleRun(request, reply, runId);
    if (access.response) return access.response;
    const actor = platformActorFromRequest(request);
    return getRuntime().store
      .listRuns()
      .filter((run) => actorCanAccessOwnedResource(actor, run) && String(run.task_msg).includes(`parent:${runId}`));
  });

  const exportHandler = async (request: FastifyRequest, reply: FastifyReply) =>
    runExport(params(request).run_id, request, reply, params(request).thread_id);
  register(app, "GET", "/api/runs/:run_id/export", exportHandler);
  register(app, "GET", "/api/threads/:thread_id/runs/:run_id/export", exportHandler);
  register(app, "GET", "/api/runs/:run_id/join", runDetail);
  register(app, "GET", "/api/threads/:thread_id/runs/:run_id/join", runDetail);

  const research = async (request: FastifyRequest, reply: FastifyReply) => {
    const runId = params(request).run_id;
    const access = accessibleRun(request, reply, runId, params(request).thread_id);
    if (access.response) return access.response;
    return { run_id: runId, status: "none", items: [], evidence: [], lineage: [] };
  };
  for (const suffix of [
    "operator-actions/lineage",
    "research/continuation",
    "research/evidence",
    "research/execution",
    "research/lineage",
    "research/review",
  ]) {
    register(app, "GET", `/api/runs/:run_id/${suffix}`, research);
    register(app, "GET", `/api/threads/:thread_id/runs/:run_id/${suffix}`, research);
  }

  const returnRun = async (request: FastifyRequest, reply: FastifyReply) => {
    const access = accessibleRun(request, reply, params(request).run_id, params(request).thread_id);
    return access.response ?? access.run;
  };
  register(app, "POST", "/api/runs/:run_id/resume", returnRun);
  register(app, "POST", "/api/runs/:run_id/input", async (request: FastifyRequest, reply: FastifyReply) =>
    submitRunInput(params(request).run_id, request, reply),
  );
  register(app, "POST", "/api/runs/:run_id/external-approval/resolve", returnRun);
  register(app, "POST", "/api/runs/:run_id/operator-actions/follow-up", returnRun);
  register(app, "POST", "/api/runs/:run_id/research/continue", returnRun);
  register(app, "POST", "/api/threads/:thread_id/runs/:run_id/input", async (request: FastifyRequest, reply: FastifyReply) =>
    submitRunInput(params(request).run_id, request, reply),
  );
  register(app, "POST", "/api/threads/:thread_id/runs/:run_id/operator-actions/follow-up", returnRun);
  register(app, "POST", "/api/threads/:thread_id/runs/:run_id/research/continue", returnRun);
  register(app, "POST", "/api/threads/:thread_id/runs/:run_id/cancel", async (request: FastifyRequest, reply: FastifyReply) =>
    cancelRun(params(request).run_id, request, reply),
  );
  register(app, "POST", "/api/runs/:run_id/external-run/resolve", async (request: FastifyRequest, reply: FastifyReply) => {
    const runId = params(request).run_id;
    const access = accessibleRun(request, reply, runId);
    if (access.response) return access.response;
    return { run_id: runId, resolved: true };
  });
  register(app, "GET", "/api/approvals", async (request: FastifyRequest) => {
    const q = query(request);
    const status = q.status === "resolved" ? undefined : q.status;
    const runtime = getRuntime();
    const actor = platformActorFromRequest(request);
    return getRuntime().store
      .listApprovals({ run_id: q.run_id, status, org_id: requestOrgId(request) })
      .filter((approval) => {
        const run = runtime.store.getRun(approval.run_id);
        return Boolean(run && actorCanAccessOwnedResource(actor, run));
      })
      .map(approvalResponse)
      .filter((approval) => (q.status ? approval.status === q.status : true));
  });
  register(app, "GET", "/api/approvals/:approval_id", async (request: FastifyRequest, reply: FastifyReply) => {
    const approval = getRuntime().store.getApproval(params(request).approval_id);
    if (!approval) return notFound(reply, "Approval not found");
    const run = getRuntime().store.getRun(approval.run_id);
    if (!run) return notFound(reply, "Run not found");
    if (!actorCanAccessOwnedResource(platformActorFromRequest(request), run)) return forbidden(reply);
    return approvalResponse(approval);
  });

  register(app, "GET", "/api/memory", async (request: FastifyRequest) =>
    listDocumentPayloads<any>("memory", requestOrgId(request)).filter((entry) => canAccessDocument(request, entry)),
  );
  register(app, "POST", "/api/memory", async (request: FastifyRequest, reply: FastifyReply) => {
    const body = (request.body ?? {}) as any;
    const entry = {
      id: `memory_${nanoid(12)}`,
      ...body,
      org_id: requestOrgId(request, body),
      owner_user_id: requestOwnerUserId(request, body),
      created_at: now(),
      updated_at: now(),
    };
    getRuntime().store.insertDocument("memory", entry.id, entry);
    reply.code(201);
    return entry;
  });
  register(app, "DELETE", "/api/memory/:memory_id", async (request: FastifyRequest) => {
    return deleteMemoryResponse(request);
  });
  register(app, "GET", "/api/memory-candidates", async (request: FastifyRequest) => {
    const q = query(request);
    return listDocumentPayloads<any>("memory_candidate", requestOrgId(request)).filter(
      (candidate) =>
        canAccessDocument(request, candidate) &&
        (!q.status || candidate.status === q.status) &&
        (!q.run_id || candidate.run_id === q.run_id),
    );
  });
  register(app, "POST", "/api/memory-candidates/:candidate_id/approve", async (request: FastifyRequest, reply: FastifyReply) => {
    const candidateId = params(request).candidate_id;
    const candidate = documentPayload<any>("memory_candidate", candidateId);
    if (!candidate || candidate.org_id !== requestOrgId(request) || !canAccessDocument(request, candidate)) {
      return notFound(reply, "Memory candidate not found");
    }
    const timestamp = now();
    const memory = {
      id: `memory_${nanoid(12)}`,
      org_id: candidate.org_id,
      owner_user_id: candidate.owner_user_id ?? requestOwnerUserId(request),
      scope: candidate.scope,
      scope_id: candidate.scope_id ?? null,
      key: candidate.key,
      value: candidate.value,
      source: "memory_candidate",
      confidence: candidate.confidence ?? null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    const resolved = { ...candidate, status: "approved", resolved_at: timestamp };
    getRuntime().store.upsertDocument("memory", memory.id, memory);
    getRuntime().store.upsertDocument("memory_candidate", candidateId, resolved);
    return { candidate_id: candidateId, status: "approved", memory_entry: memory, candidate: resolved };
  });
  register(app, "POST", "/api/memory-candidates/:candidate_id/reject", async (request: FastifyRequest, reply: FastifyReply) => {
    const candidateId = params(request).candidate_id;
    const candidate = documentPayload<any>("memory_candidate", candidateId);
    if (!candidate || candidate.org_id !== requestOrgId(request) || !canAccessDocument(request, candidate)) {
      return notFound(reply, "Memory candidate not found");
    }
    const resolved = { ...candidate, status: "rejected", resolved_at: now() };
    getRuntime().store.upsertDocument("memory_candidate", candidateId, resolved);
    return { candidate_id: candidateId, status: "rejected", candidate: resolved };
  });
  register(app, "GET", "/api/long-term-memory/health", async () => ({
    status: "ok",
    enabled: false,
  }));
  register(app, "DELETE", "/api/long-term-memory/:memory_id", async (request: FastifyRequest) => {
    return deleteMemoryResponse(request);
  });

  register(app, "GET", "/api/model-profiles", async (request: FastifyRequest) => {
    const orgId = requestOrgId(request);
    const stored = listDocumentPayloads<any>("model_profile_entry", orgId)
      .filter((profile) => canAccessDocument(request, profile))
      .sort((a, b) => String(a.key).localeCompare(String(b.key)));
    return stored.length > 0 ? stored : [defaultModelProfile()];
  });
  register(app, "GET", "/api/model-profiles/:profile_id_or_key", async (request: FastifyRequest, reply: FastifyReply) =>
    accessibleModelProfileByIdOrKey(request, params(request).profile_id_or_key) ??
    notFound(reply, "Model profile not found"),
  );
  register(app, "POST", "/api/model-profiles", async (request: FastifyRequest, reply: FastifyReply) => {
    const body = (request.body ?? {}) as any;
    const profile = createModelProfileFromBody(request, body);
    getRuntime().store.insertDocument("model_profile_entry", profile.id, profile);
    reply.code(201);
    return profile;
  });
  register(app, "PATCH", "/api/model-profiles/:profile_id_or_key", async (request: FastifyRequest, reply: FastifyReply) => {
    const orgId = requestOrgId(request);
    const existing = modelProfileByIdOrKey(orgId, params(request).profile_id_or_key);
    if (!existing) return notFound(reply, "Model profile not found");
    if (!canAccessDocument(request, existing)) return forbidden(reply);
    const body = (request.body ?? {}) as any;
    const authSecret =
      Object.prototype.hasOwnProperty.call(body, "auth_secret")
        ? resolveModelProfileSecret(body.auth_secret, orgId, existing.key)
        : existing.auth_secret;
    const updated = {
      ...existing,
      ...body,
      id: existing.id,
      org_id: orgId,
      owner_user_id: existing.owner_user_id ?? requestOwnerUserId(request),
      key: existing.key,
      auth_secret: authSecret,
      updated_at: now(),
    };
    getRuntime().store.upsertDocument("model_profile_entry", existing.id, updated, documentWriteGuard(request));
    return updated;
  });
  for (const enabled of [true, false]) {
    register(
      app,
      "POST",
      `/api/model-profiles/:profile_id_or_key/${enabled ? "enable" : "disable"}`,
      async (request: FastifyRequest, reply: FastifyReply) => {
        const orgId = requestOrgId(request);
        const existing = modelProfileByIdOrKey(orgId, params(request).profile_id_or_key);
        if (!existing) return notFound(reply, "Model profile not found");
        if (!canAccessDocument(request, existing)) return forbidden(reply);
        const profile = { ...existing, enabled, updated_at: now() };
        getRuntime().store.upsertDocument("model_profile_entry", profile.id, profile, documentWriteGuard(request));
        return { id: profile.id, org_id: profile.org_id, key: profile.key, enabled, profile };
      },
    );
  }

  register(app, "GET", "/api/skills", async (request: FastifyRequest) =>
    skillRegistryEntries(request).map(skillPackageFromEntry),
  );
  register(app, "GET", "/api/skills/:skill_key_or_ref", async (request: FastifyRequest) =>
    skillPackageFromEntry(skillRegistryEntryForRequest(request, params(request).skill_key_or_ref)),
  );
  register(app, "GET", "/api/skill-registry", async (request: FastifyRequest) =>
    skillRegistryEntries(request),
  );
  register(app, "GET", "/api/skill-registry/:entry_id_or_key", async (request: FastifyRequest) =>
    skillRegistryEntryForRequest(request, params(request).entry_id_or_key),
  );
  register(app, "POST", "/api/skill-registry", async (request: FastifyRequest, reply: FastifyReply) => {
    const body = (request.body ?? {}) as any;
    const entry = {
      ...skillEntry(body.key ?? "custom"),
      ...body,
      org_id: requestOrgId(request, body),
      owner_user_id: requestOwnerUserId(request, body),
    };
    getRuntime().store.insertDocument("skill_registry_entry", entry.id, entry);
    reply.code(201);
    return entry;
  });
  register(app, "POST", "/api/skill-registry/user", async (request: FastifyRequest, reply: FastifyReply) => {
    const body = (request.body ?? {}) as any;
    const actor = requestActorUserId(platformActorFromRequest(request), body);
    const key = body.key ?? "user";
    const entry = {
      ...skillEntry(key),
      ...body,
      id: `skill_package_${requestOrgId(request, body)}_${actor}_${key}`,
      org_id: requestOrgId(request, body),
      owner_user_id: actor,
      source: "user",
      read_only: false,
    };
    getRuntime().store.insertDocument("skill_package_user", `${entry.org_id}:${actor}:${key}`, entry);
    reply.code(201);
    return entry;
  });
  register(app, "PATCH", "/api/skill-registry/:entry_id_or_key", async (request: FastifyRequest, reply: FastifyReply) =>
    saveSkillRegistryEntry(request, reply, params(request).entry_id_or_key, (request.body ?? {}) as Record<string, unknown>),
  );
  register(app, "PATCH", "/api/skill-registry/user/:skill_key", async (request: FastifyRequest) => {
    const orgId = requestOrgId(request);
    const actor = requestActorUserId(platformActorFromRequest(request));
    const key = params(request).skill_key;
    const id = `${orgId}:${actor}:${key}`;
    const existing = documentPayload<any>("skill_package_user", id) ?? {
      ...skillEntry(key),
      id: `skill_package_${orgId}_${actor}_${key}`,
      org_id: orgId,
      owner_user_id: actor,
      source: "user",
      read_only: false,
    };
    const updated = {
      ...existing,
      ...((request.body ?? {}) as any),
      org_id: orgId,
      owner_user_id: actor,
      updated_at: now(),
    };
    getRuntime().store.upsertDocument("skill_package_user", id, updated, documentWriteGuard(request));
    return updated;
  });
  for (const enabled of [true, false]) {
    register(
      app,
      "POST",
      `/api/skill-registry/:entry_id_or_key/${enabled ? "enable" : "disable"}`,
      async (request: FastifyRequest, reply: FastifyReply) => {
        const entry = saveSkillRegistryEntry(request, reply, params(request).entry_id_or_key, { enabled });
        if ("error" in entry) return entry;
        return {
          id: entry.id,
          org_id: entry.org_id,
          key: entry.key,
          enabled,
          status: entry.status,
          runtime_visible: enabled,
          entry,
        };
      },
    );
  }
  register(app, "GET", "/api/subagents", async (request: FastifyRequest) =>
    listDocumentPayloads<any>("subagent_spec", requestOrgId(request)).filter((spec) => canAccessDocument(request, spec)),
  );
  register(app, "GET", "/api/subagents/:key", async (request: FastifyRequest, reply: FastifyReply) => {
    const orgId = requestOrgId(request);
    const key = params(request).key;
    const spec = listDocumentPayloads<any>("subagent_spec", orgId).find(
      (item) => item.key === key && canAccessDocument(request, item),
    );
    return spec ?? notFound(reply, "Subagent not found");
  });
  register(app, "POST", "/api/subagents", async (request: FastifyRequest, reply: FastifyReply) => {
    const body = (request.body ?? {}) as any;
    const spec = {
      id: `subagent_spec_${nanoid(12)}`,
      ...body,
      org_id: requestOrgId(request, body),
      owner_user_id: requestOwnerUserId(request, body),
      key: body.key ?? `subagent_${nanoid(8)}`,
      name: body.name ?? body.key ?? "Subagent",
      instructions: body.instructions ?? "",
      allowed_tools: Array.isArray(body.allowed_tools) ? body.allowed_tools : [],
      created_at: now(),
      updated_at: now(),
    };
    getRuntime().store.insertDocument("subagent_spec", spec.id, spec);
    reply.code(201);
    return spec;
  });

  register(app, "GET", "/api/external-tools/configs", async (request: FastifyRequest) => {
    const orgId = requestOrgId(request);
    return [
      externalToolConfig("local-capabilities", true, await localToolCatalog()),
      ...listDocumentPayloads<any>("external_tool_config_entry", orgId)
        .filter((config) => canAccessDocument(request, config))
        .sort((a, b) => String(a.key).localeCompare(String(b.key))),
    ];
  });
  register(app, "GET", "/api/external-tools/configs/:config_id_or_key", async (request: FastifyRequest, reply: FastifyReply) => {
    const key = params(request).config_id_or_key;
    if (key === "local-capabilities") return externalToolConfig(key, true, await localToolCatalog());
    return accessibleExternalToolByIdOrKey(request, key) ?? notFound(reply, "External tool config not found");
  });
  register(app, "POST", "/api/external-tools/configs", async (request: FastifyRequest, reply: FastifyReply) => {
    const config = externalToolConfigFromBody(request, (request.body ?? {}) as any);
    getRuntime().store.insertDocument("external_tool_config_entry", config.id, config);
    reply.code(201);
    return config;
  });
  register(app, "PATCH", "/api/external-tools/configs/:config_id_or_key", async (request: FastifyRequest, reply: FastifyReply) => {
    const existing = externalToolByIdOrKey(requestOrgId(request), params(request).config_id_or_key);
    if (!existing) return notFound(reply, "External tool config not found");
    if (!canAccessDocument(request, existing)) return forbidden(reply);
    const ownerUserId = requestOwnerUserId(request);
    const updated = resolveExternalToolSecrets({
      ...existing,
      ...((request.body ?? {}) as any),
      id: existing.id,
      key: existing.key,
      org_id: existing.org_id,
      owner_user_id: existing.owner_user_id ?? ownerUserId,
      activation_status: "pending_runtime_reload",
      updated_at: now(),
      updated_by: ownerUserId,
    }, existing.org_id, existing.key);
    getRuntime().store.upsertDocument("external_tool_config_entry", existing.id, updated, documentWriteGuard(request));
    return updated;
  });
  register(app, "POST", "/api/external-tools/configs/:config_id_or_key/enable", async (request: FastifyRequest, reply: FastifyReply) => {
    const existing = externalToolByIdOrKey(requestOrgId(request), params(request).config_id_or_key);
    if (!existing) return externalToolOperation(params(request).config_id_or_key, "enable", true);
    if (!canAccessDocument(request, existing)) return forbidden(reply);
    const config = { ...existing, enabled: true, updated_at: now(), activation_status: "pending_runtime_reload" };
    getRuntime().store.upsertDocument("external_tool_config_entry", existing.id, config, documentWriteGuard(request));
    return { action: "enable", config, audit_event: { id: `audit_${nanoid(8)}`, action: "enable", at: now(), actor_user_id: requestOwnerUserId(request) } };
  });
  register(app, "POST", "/api/external-tools/configs/:config_id_or_key/disable", async (request: FastifyRequest, reply: FastifyReply) => {
    const existing = externalToolByIdOrKey(requestOrgId(request), params(request).config_id_or_key);
    if (!existing) return externalToolOperation(params(request).config_id_or_key, "disable", false);
    if (!canAccessDocument(request, existing)) return forbidden(reply);
    const config = { ...existing, enabled: false, updated_at: now(), activation_status: "pending_runtime_reload" };
    getRuntime().store.upsertDocument("external_tool_config_entry", existing.id, config, documentWriteGuard(request));
    return { action: "disable", config, audit_event: { id: `audit_${nanoid(8)}`, action: "disable", at: now(), actor_user_id: requestOwnerUserId(request) } };
  });
  register(app, "POST", "/api/external-tools/configs/:config_id_or_key/reset-cache", async (request: FastifyRequest, reply: FastifyReply) => {
    const existing = externalToolByIdOrKey(requestOrgId(request), params(request).config_id_or_key);
    if (!existing) return externalToolOperation(params(request).config_id_or_key, "reset_cache", true);
    if (!canAccessDocument(request, existing)) return forbidden(reply);
    const config = { ...existing, cache_status: { status: "empty", last_reset_at: now() }, updated_at: now() };
    getRuntime().store.upsertDocument("external_tool_config_entry", existing.id, config, documentWriteGuard(request));
    return { action: "reset_cache", config, audit_event: { id: `audit_${nanoid(8)}`, action: "reset_cache", at: now(), actor_user_id: requestOwnerUserId(request) } };
  });

  register(app, "GET", "/api/workspaces/:workspace_id/files", async (request: FastifyRequest) =>
    getRuntime().store.listWorkspaceFiles(params(request).workspace_id).map(workspaceFile),
  );
  register(app, "GET", "/api/workspaces/:workspace_id/files/:path", async (request: FastifyRequest, reply: FastifyReply) => {
    const file = getRuntime().store.readFile(params(request).workspace_id, params(request).path);
    return file
      ? { path: file.path, content: file.content, media_type: workspaceMediaTypeForPath(file.path) }
      : notFound(reply, "Workspace file not found");
  });
  register(app, "GET", "/api/workspaces/:workspace_id/files/:path/content", async (request: FastifyRequest, reply: FastifyReply) => {
    const file = getRuntime().store.readFile(params(request).workspace_id, params(request).path);
    if (!file) return notFound(reply, "Workspace file not found");
    reply.header("content-type", workspaceContentTypeForPath(file.path));
    return file.content;
  });
  register(app, "GET", "/api/workspaces/:workspace_id/files/:path/download", async (request: FastifyRequest, reply: FastifyReply) => {
    const file = getRuntime().store.readFile(params(request).workspace_id, params(request).path);
    if (!file) return notFound(reply, "Workspace file not found");
    reply.header("content-type", "application/octet-stream");
    return file.content;
  });
  register(app, "GET", "/api/workspaces/:workspace_id/files/:path/versions", async (request: FastifyRequest, reply: FastifyReply) => {
    const file = getRuntime().store.readFile(params(request).workspace_id, params(request).path);
    if (!file) return notFound(reply, "Workspace file not found");
    return [{
      ...workspaceFile(file),
      operation: "write",
      created_at: file.created_at,
    }];
  });
  register(app, "PUT", "/api/workspaces/:workspace_id/files/:path", async (request: FastifyRequest) => {
    const body = (request.body ?? {}) as any;
    const file = getRuntime().store.writeFile(
      params(request).workspace_id,
      params(request).path,
      String(body.content ?? ""),
    );
    return workspaceFile(file);
  });
  register(app, "DELETE", "/api/workspaces/:workspace_id/files/:path", async (request: FastifyRequest) => {
    getRuntime().store.deleteFile(params(request).workspace_id, params(request).path);
    return { path: params(request).path };
  });
  register(app, "POST", "/api/workspaces/:workspace_id/files/:path/patch", async (request: FastifyRequest, reply: FastifyReply) => {
    return applyWorkspaceFilePatch(request, reply, params(request).workspace_id, params(request).path);
  });
  register(app, "POST", "/api/workspaces/:workspace_id/files/:path/convert", async (request: FastifyRequest, reply: FastifyReply) => {
    const file = getRuntime().store.readFile(params(request).workspace_id, params(request).path);
    if (!file) return notFound(reply, "Workspace file not found");
    return {
      workspace_id: file.workspace_id,
      source_path: file.path,
      source_media_type: workspaceMediaTypeForPath(file.path),
      source_size: file.size,
      output_file: null,
      skipped: true,
    };
  });
  register(app, "POST", "/api/workspaces/:workspace_id/files/:path/promote", async (request: FastifyRequest) => ({
    workspace_id: params(request).workspace_id,
    path: params(request).path,
    promoted: false,
  }));
  register(app, "GET", "/api/workspaces/:workspace_id/files/*", workspaceFileWildcardRequest);
  register(app, "PUT", "/api/workspaces/:workspace_id/files/*", workspaceFileWildcardRequest);
  register(app, "DELETE", "/api/workspaces/:workspace_id/files/*", workspaceFileWildcardRequest);
  register(app, "POST", "/api/workspaces/:workspace_id/files/*", workspaceFileWildcardRequest);
  register(app, "POST", "/api/workspaces/:workspace_id/uploads", async (request: FastifyRequest) => {
    const body = (request.body ?? {}) as any;
    const path = String(body.path ?? `upload_${nanoid(8)}.txt`);
    const content = body.content_base64
      ? Buffer.from(String(body.content_base64), "base64").toString("utf8")
      : "";
    const file = getRuntime().store.writeFile(params(request).workspace_id, path, content);
    return {
      workspace_id: file.workspace_id,
      path: file.path,
      file: workspaceFile(file),
      size: file.size,
      media_type: body.media_type ?? "text/plain",
      content_encoding: "base64",
      source: "api",
      overwritten: file.version > 1,
      conversion: null,
    };
  });
  register(app, "GET", "/api/workspaces/:workspace_id/snapshot", async (request: FastifyRequest) =>
    workspaceSnapshot(params(request).workspace_id),
  );
  register(app, "GET", "/api/workspaces/:workspace_id/diff", async (request: FastifyRequest) => ({
    workspace_id: params(request).workspace_id,
    changes: [],
  }));
  register(app, "POST", "/api/workspaces/:workspace_id/restore", async (request: FastifyRequest) => ({
    workspace_id: params(request).workspace_id,
    target_version: Number(((request.body ?? {}) as any).version ?? 1),
    restored_version: 1,
    changes: [],
    restored_count: 0,
    deleted_count: 0,
    unchanged_count: 0,
  }));
  register(app, "GET", "/api/workspaces/:workspace_id/images/:path/view", async (request: FastifyRequest, reply: FastifyReply) => {
    const file = getRuntime().store.readFile(params(request).workspace_id, params(request).path);
    if (!file) return notFound(reply, "Workspace file not found");
    return {
      workspace_id: file.workspace_id,
      path: file.path,
      media_type: workspaceMediaTypeForPath(file.path),
      size: file.size,
      content_hash: null,
      content_encoding: "base64",
      content_base64: Buffer.from(file.content, "utf8").toString("base64"),
    };
  });
}
