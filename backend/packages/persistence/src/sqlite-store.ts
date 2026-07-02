import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import initSqlJs, { type Database as SqlJsDatabase } from "sql.js";
import type { AgentStore } from "./protocols.js";
import type {
  AgentThread,
  AgentMessage,
  AgentRun,
  AgentStreamEvent,
} from "@aithru-agent/contracts";
import type {
  WorkspaceFile,
  WorkspaceAccessGuard,
  WorkspaceBinding,
  WorkspaceListFilter,
  WorkspaceWriteOptions,
  AgentTodo,
  AgentApproval,
  AgentDocument,
  AgentContextSummary,
  DocumentWriteGuard,
} from "./store.js";
import { runMigrations } from "./migrations.js";
import { FileWorkspaceStore } from "./workspace-files.js";

type SqliteParam = string | number | null;
type SqliteRow = Record<string, unknown>;

const RUN_COLUMNS = [
  "org_id",
  "actor_user_id",
  "source",
  "thread_id",
  "workspace_id",
  "task_msg",
  "scopes",
  "harness_options",
  "status",
  "started_at",
  "completed_at",
  "current_approval_id",
  "claim_worker_id",
  "claim_claimed_at",
  "claim_heartbeat_at",
  "claim_lease_expires_at",
  "claim_attempt",
  "retry_policy",
  "retry_state",
  "result",
  "error",
] as const;

const DOCUMENT_TABLES = {
  model_profile_entry: "model_profiles",
  skill_registry_entry: "skill_registry_entries",
  skill_package_user: "skill_package_users",
  subagent_spec: "subagent_specs",
  external_tool_config_entry: "external_tool_configs",
  tool_call_record: "tool_call_records",
} as const;

type DocumentKind = keyof typeof DOCUMENT_TABLES;

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function jsonOrNull(value: unknown): string | null {
  return value == null ? null : JSON.stringify(value);
}

function parseJson<T>(value: unknown, fallback: T): T {
  if (typeof value !== "string" || value.length === 0) return fallback;
  return JSON.parse(value) as T;
}

function validateSecretRef(secretRef: string): void {
  if (!secretRef.startsWith("secret://")) {
    throw new Error("secret_ref must be a secret:// reference");
  }
}

function workspaceIdForThread(threadId: string): string {
  return `ws_thread_${threadId}`;
}

export class SqliteStore implements AgentStore {
  private closed = false;
  private workspaceFiles = new FileWorkspaceStore();
  private volatileDocuments = new Map<string, Map<string, unknown>>();

  /**
   * Create and initialise a SqliteStore.
   *
   * `dbPath` is durable: the file is read at startup and rewritten after each
   * mutation. Passing a Uint8Array keeps the old restore-from-buffer path.
   */
  static async create(source?: string | Uint8Array): Promise<SqliteStore> {
    const SQL = await initSqlJs();
    const dbPath = typeof source === "string" ? source : undefined;
    const buffer =
      source instanceof Uint8Array
        ? source
        : dbPath && dbPath !== ":memory:" && existsSync(dbPath)
          ? readFileSync(dbPath)
          : undefined;
    const sqlite = new SQL.Database(buffer);
    const store = new SqliteStore(sqlite, dbPath);
    runMigrations(store);
    store.migrateSettingsOrgScope();
    store.migrateSecretsOrgScope();
    store.migrateChildEntityIdentity();
    for (const table of Object.values(DOCUMENT_TABLES)) {
      store.ensureColumn(table, "owner_user_id", "TEXT");
    }
    store.persist();
    return store;
  }

  private constructor(
    private sqlite: SqlJsDatabase,
    private dbPath?: string,
  ) {
    this.secretKey = this.loadSecretKey();
  }

  private secretKey: Buffer;

  exec(sql: string): void {
    this.sqlite.run(sql);
  }

  // ── Threads ──────────────────────────────────────────────────────────

  createThread(thread: AgentThread): AgentThread {
    this.runStatement(
      `INSERT INTO threads
        (id, org_id, owner_user_id, title, status, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        thread.id,
        thread.org_id,
        thread.owner_user_id,
        thread.title ?? null,
        String(thread.status),
        thread.created_at,
        thread.updated_at,
      ],
    );
    this.bindWorkspace(workspaceIdForThread(thread.id), {
      org_id: thread.org_id,
      owner_user_id: thread.owner_user_id,
      thread_id: thread.id,
    });
    return thread;
  }

  getThread(id: string): AgentThread | undefined {
    return this.selectOne<AgentThread>(
      "SELECT * FROM threads WHERE id = ?",
      [id],
    );
  }

  listThreads(orgId?: string): AgentThread[] {
    return orgId
      ? this.selectAll<AgentThread>(
          "SELECT * FROM threads WHERE org_id = ? ORDER BY created_at ASC",
          [orgId],
        )
      : this.selectAll<AgentThread>(
          "SELECT * FROM threads ORDER BY created_at ASC",
        );
  }

  updateThread(id: string, patch: Partial<AgentThread>): AgentThread {
    this.updateRow("threads", "id = ?", [id], patch, [
      "org_id",
      "owner_user_id",
      "title",
      "status",
      "created_at",
      "updated_at",
    ]);
    const updated = this.getThread(id);
    if (!updated) throw new Error(`Thread ${id} not found`);
    return updated;
  }

  // ── Messages ─────────────────────────────────────────────────────────

  createMessage(msg: AgentMessage): AgentMessage {
    const thread = this.getThread(msg.thread_id);
    const run = msg.run_id ? this.getRun(msg.run_id) : undefined;
    const stored = {
      ...msg,
      org_id: thread?.org_id ?? run?.org_id ?? msg.org_id ?? null,
      actor_user_id: run?.actor_user_id ?? thread?.owner_user_id ?? msg.actor_user_id ?? null,
    };
    this.runStatement(
      `INSERT INTO messages
        (id, org_id, actor_user_id, thread_id, role, content, run_id, workspace_paths, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        stored.id,
        stored.org_id ?? null,
        stored.actor_user_id ?? null,
        stored.thread_id,
        String(stored.role),
        stored.content,
        stored.run_id ?? null,
        JSON.stringify(stored.workspace_paths),
        stored.created_at,
      ],
    );
    return stored;
  }

  getMessage(id: string): AgentMessage | undefined {
    const row = this.selectOne<SqliteRow>(
      "SELECT * FROM messages WHERE id = ?",
      [id],
    );
    return row ? this.hydrateMessage(row) : undefined;
  }

  listMessages(threadId: string, orgId?: string): AgentMessage[] {
    const where = orgId ? "thread_id = ? AND org_id = ?" : "thread_id = ?";
    const params = orgId ? [threadId, orgId] : [threadId];
    return this.selectAll<SqliteRow>(
      `SELECT * FROM messages WHERE ${where} ORDER BY created_at ASC`,
      params,
    ).map((row) => this.hydrateMessage(row));
  }

  // ── Runs ─────────────────────────────────────────────────────────────

  createRun(run: AgentRun): AgentRun {
    this.runStatement(
      `INSERT INTO runs
        (id, org_id, actor_user_id, source, thread_id, workspace_id,
         task_msg, scopes, harness_options, status, started_at, completed_at,
         current_approval_id, claim_worker_id, claim_claimed_at,
         claim_heartbeat_at, claim_lease_expires_at, claim_attempt,
         retry_policy, retry_state, result, error)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        run.id,
        run.org_id,
        run.actor_user_id,
        String(run.source),
        run.thread_id ?? null,
        run.workspace_id,
        run.task_msg,
        JSON.stringify(run.scopes),
        jsonOrNull(run.harness_options),
        String(run.status),
        run.started_at,
        run.completed_at ?? null,
        run.current_approval_id ?? null,
        run.claim?.worker_id ?? null,
        run.claim?.claimed_at ?? null,
        run.claim?.last_heartbeat_at ?? null,
        run.claim?.lease_expires_at ?? null,
        run.claim?.attempt ?? null,
        jsonOrNull((run as any).retry_policy),
        jsonOrNull((run as any).retry_state),
        jsonOrNull(run.result),
        jsonOrNull(run.error),
      ],
    );
    const thread = run.thread_id ? this.getThread(run.thread_id) : undefined;
    this.bindWorkspace(run.workspace_id, {
      org_id: run.org_id,
      owner_user_id: thread?.owner_user_id ?? run.actor_user_id,
      thread_id: run.thread_id,
    });
    return run;
  }

  getRun(id: string): AgentRun | undefined {
    const row = this.selectOne<SqliteRow>(
      "SELECT * FROM runs WHERE id = ?",
      [id],
    );
    return row ? this.hydrateRun(row) : undefined;
  }

  listRuns(filter?: { org_id?: string; thread_id?: string }): AgentRun[] {
    const where: string[] = [];
    const params: SqliteParam[] = [];
    if (filter?.org_id) {
      where.push("org_id = ?");
      params.push(filter.org_id);
    }
    if (filter?.thread_id) {
      where.push("thread_id = ?");
      params.push(filter.thread_id);
    }
    const clause = where.length ? `WHERE ${where.join(" AND ")}` : "";
    return this.selectAll<SqliteRow>(
      `SELECT * FROM runs ${clause} ORDER BY started_at ASC`,
      params,
    ).map((row) => this.hydrateRun(row));
  }

  updateRun(id: string, patch: Partial<AgentRun>): AgentRun {
    const flat: Record<string, unknown> = { ...patch };
    if ("scopes" in patch) flat.scopes = JSON.stringify(patch.scopes);
    if ("harness_options" in patch)
      flat.harness_options = jsonOrNull(patch.harness_options);
    if ("result" in patch) flat.result = jsonOrNull(patch.result);
    if ("error" in patch) flat.error = jsonOrNull(patch.error);
    if ("claim" in patch) {
      flat.claim_worker_id = patch.claim?.worker_id ?? null;
      flat.claim_claimed_at = patch.claim?.claimed_at ?? null;
      flat.claim_heartbeat_at = patch.claim?.last_heartbeat_at ?? null;
      flat.claim_lease_expires_at = patch.claim?.lease_expires_at ?? null;
      flat.claim_attempt = patch.claim?.attempt ?? null;
    }
    if ("retry_policy" in (patch as any))
      flat.retry_policy = jsonOrNull((patch as any).retry_policy);
    if ("retry_state" in (patch as any))
      flat.retry_state = jsonOrNull((patch as any).retry_state);
    delete flat.claim;

    this.updateRow("runs", "id = ?", [id], flat, [...RUN_COLUMNS]);
    const updated = this.getRun(id);
    if (!updated) throw new Error(`Run ${id} not found`);
    return updated;
  }

  // ── Events ───────────────────────────────────────────────────────────

  appendEvent(runId: string, event: AgentStreamEvent): void {
    const run = this.getRun(runId);
    const stored = {
      ...event,
      org_id: run?.org_id ?? event.org_id ?? null,
      actor_user_id: run?.actor_user_id ?? event.actor_user_id ?? null,
    };
    this.runStatement(
      `INSERT INTO events
        (id, org_id, actor_user_id, run_id, thread_id, sequence, timestamp, type, source_kind,
         source_id, source_name, visibility, redaction, summary, payload)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        stored.id,
        stored.org_id ?? null,
        stored.actor_user_id ?? null,
        runId,
        stored.thread_id ?? null,
        stored.sequence,
        stored.timestamp,
        stored.type,
        stored.source.kind,
        stored.source.id ?? null,
        stored.source.name ?? null,
        stored.visibility,
        stored.redaction,
        stored.summary ?? null,
        JSON.stringify(stored.payload),
      ],
    );
  }

  nextEventSequence(runId: string): number {
    const row = this.selectOne<{ sequence: number | null }>(
      "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM events WHERE run_id = ?",
      [runId],
    );
    return Number(row?.sequence ?? 1);
  }

  listEvents(runId: string): AgentStreamEvent[] {
    return this.selectAll<SqliteRow>(
      "SELECT * FROM events WHERE run_id = ? ORDER BY sequence ASC",
      [runId],
    ).map((row) => this.hydrateEvent(row));
  }

  // ── Workspace ────────────────────────────────────────────────────────

  writeFile(
    workspaceId: string,
    path: string,
    content: string,
    options?: WorkspaceWriteOptions,
  ): WorkspaceFile {
    return this.workspaceFiles.writeFile(workspaceId, path, content, options);
  }

  readFile(workspaceId: string, path: string, guard?: WorkspaceAccessGuard): WorkspaceFile | undefined {
    return this.workspaceFiles.readFile(workspaceId, path, guard);
  }

  listWorkspaceFiles(workspaceId: string, filter?: WorkspaceListFilter): WorkspaceFile[] {
    return this.workspaceFiles.listWorkspaceFiles(workspaceId, filter);
  }

  deleteFile(workspaceId: string, path: string, guard?: WorkspaceAccessGuard): boolean {
    return this.workspaceFiles.deleteFile(workspaceId, path, guard);
  }

  getWorkspaceRoot(workspaceId: string, guard?: WorkspaceAccessGuard): string {
    return this.workspaceFiles.getWorkspaceRoot(workspaceId, guard);
  }

  bindWorkspace(workspaceId: string, binding: Omit<WorkspaceBinding, "workspace_id">): WorkspaceBinding {
    return this.workspaceFiles.bindWorkspace(workspaceId, binding);
  }

  getWorkspaceBinding(workspaceId: string): WorkspaceBinding | undefined {
    return this.workspaceFiles.getWorkspaceBinding(workspaceId);
  }

  canAccessWorkspace(workspaceId: string, guard?: WorkspaceAccessGuard): boolean {
    return this.workspaceFiles.canAccessWorkspace(workspaceId, guard);
  }

  // ── Todos ────────────────────────────────────────────────────────────

  createTodo(todo: AgentTodo): AgentTodo {
    const run = this.getRun(todo.run_id);
    const threadId = todo.thread_id ?? run?.thread_id ?? null;
    const stored = {
      ...todo,
      org_id: run?.org_id ?? todo.org_id ?? null,
      actor_user_id: run?.actor_user_id ?? todo.actor_user_id ?? null,
      thread_id: threadId,
    };
    this.runStatement(
      `INSERT INTO todos
        (id, org_id, actor_user_id, thread_id, run_id, title, status, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        stored.id,
        stored.org_id ?? null,
        stored.actor_user_id ?? null,
        stored.thread_id ?? null,
        stored.run_id,
        stored.title,
        stored.status,
        stored.created_at,
        stored.updated_at,
      ],
    );
    return stored;
  }

  updateTodo(
    runId: string,
    todoId: string,
    patch: Partial<AgentTodo>,
  ): AgentTodo {
    const scope = this.todoScope(runId);
    this.updateRow("todos", `id = ? AND ${scope.column} = ? AND org_id = ?`, [todoId, scope.value, scope.orgId], {
      ...patch,
      updated_at: nowIso(),
    }, ["org_id", "actor_user_id", "thread_id", "run_id", "title", "status", "created_at", "updated_at"]);
    const todo = this.selectOne<AgentTodo>(
      `SELECT * FROM todos WHERE id = ? AND ${scope.column} = ? AND org_id = ?`,
      [todoId, scope.value, scope.orgId],
    );
    if (!todo) throw new Error(`Todo ${todoId} not found`);
    return todo;
  }

  listTodos(runId: string): AgentTodo[] {
    const scope = this.todoScope(runId);
    return this.selectAll<AgentTodo>(
      `SELECT * FROM todos WHERE ${scope.column} = ? AND org_id = ? ORDER BY created_at ASC`,
      [scope.value, scope.orgId],
    );
  }

  // ── Approvals ────────────────────────────────────────────────────────

  createApproval(approval: AgentApproval): AgentApproval {
    const run = this.getRun(approval.run_id);
    const stored = {
      ...approval,
      org_id: run?.org_id ?? approval.org_id ?? null,
      actor_user_id: run?.actor_user_id ?? approval.actor_user_id ?? null,
    };
    this.runStatement(
      `INSERT INTO approvals
        (id, org_id, actor_user_id, run_id, tool_call_id, tool_name, status, created_at, resolved_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        stored.id,
        stored.org_id ?? null,
        stored.actor_user_id ?? null,
        stored.run_id,
        stored.tool_call_id,
        stored.tool_name,
        stored.status,
        stored.created_at,
        stored.resolved_at ?? null,
      ],
    );
    return stored;
  }

  getApproval(id: string): AgentApproval | undefined {
    return this.selectOne<AgentApproval>(
      "SELECT * FROM approvals WHERE id = ?",
      [id],
    );
  }

  listApprovals(filter?: { run_id?: string; status?: string; org_id?: string }): AgentApproval[] {
    const where: string[] = [];
    const params: SqliteParam[] = [];
    const orgId = filter?.org_id ?? (filter?.run_id ? this.getRun(filter.run_id)?.org_id : undefined);
    if (orgId) {
      where.push("org_id = ?");
      params.push(orgId);
    }
    if (filter?.run_id) {
      where.push("run_id = ?");
      params.push(filter.run_id);
    }
    if (filter?.status) {
      where.push("status = ?");
      params.push(filter.status);
    }
    const clause = where.length ? `WHERE ${where.join(" AND ")}` : "";
    return this.selectAll<AgentApproval>(
      `SELECT * FROM approvals ${clause} ORDER BY created_at ASC`,
      params,
    );
  }

  resolveApproval(
    id: string,
    status: "approved" | "denied",
  ): AgentApproval {
    this.runStatement(
      "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ?",
      [status, nowIso(), id],
    );
    const approval = this.getApproval(id);
    if (!approval) throw new Error(`Approval ${id} not found`);
    return approval;
  }

  // ── Generic Documents ────────────────────────────────────────────────

  upsertDocument(kind: string, id: string, payload: unknown, guard?: DocumentWriteGuard): AgentDocument {
    const existing = this.getDocument(kind, id);
    if (existing && !documentMatchesGuard(existing.payload, guard)) {
      throw new Error(`Document not found: ${kind}/${id}`);
    }
    if (!documentMatchesGuard(payload, guard)) throw new Error(`Document not found: ${kind}/${id}`);
    const table = this.documentTable(kind);
    if (!table) {
      this.setVolatileDocument(kind, id, payload);
      return { kind, id, payload };
    }
    const fields = documentFields(payload);
    this.runStatement(
      `INSERT OR REPLACE INTO ${table} (id, org_id, owner_user_id, key, payload)
       VALUES (?, ?, ?, ?, ?)`,
      [id, fields.orgId, fields.ownerUserId, fields.key, JSON.stringify(payload)],
    );
    return { kind, id, payload };
  }

  insertDocument(kind: string, id: string, payload: unknown, guard?: DocumentWriteGuard): AgentDocument {
    const existing = this.getDocument(kind, id);
    if (existing && !documentMatchesGuard(existing.payload, guard)) throw new Error(`Document not found: ${kind}/${id}`);
    if (existing) throw new Error(`Document already exists: ${kind}/${id}`);
    return this.upsertDocument(kind, id, payload, guard);
  }

  getDocument(kind: string, id: string): AgentDocument | undefined {
    const table = this.documentTable(kind);
    if (!table) return this.getVolatileDocument(kind, id);
    const row = this.selectOne<SqliteRow>(
      `SELECT id, payload FROM ${table} WHERE id = ?`,
      [id],
    );
    return row
      ? { kind, id: String(row.id), payload: parseJson(row.payload, null) }
      : undefined;
  }

  listDocuments(kind: string, orgId: string): AgentDocument[] {
    const table = this.documentTable(kind);
    if (!table) return this.listVolatileDocuments(kind, orgId);
    return this.selectAll<SqliteRow>(
      `SELECT id, payload FROM ${table} WHERE org_id = ? ORDER BY id ASC`,
      [orgId],
    ).map((row) => ({
      kind,
      id: String(row.id),
      payload: parseJson(row.payload, null),
    }));
  }

  deleteDocument(kind: string, id: string, guard?: DocumentWriteGuard): number {
    const table = this.documentTable(kind);
    if (!table) return this.deleteVolatileDocument(kind, id, guard);
    const where = ["id = ?"];
    const params: SqliteParam[] = [id];
    if (guard?.orgId) {
      where.push("org_id = ?");
      params.push(guard.orgId);
    }
    if (guard?.ownerUserId) {
      where.push("owner_user_id = ?");
      params.push(guard.ownerUserId);
    }
    return this.runStatement(`DELETE FROM ${table} WHERE ${where.join(" AND ")}`, params);
  }

  createContextSummary(summary: AgentContextSummary): AgentContextSummary {
    const run = this.getRun(summary.run_id);
    const stored = {
      ...summary,
      org_id: run?.org_id ?? summary.org_id,
      actor_user_id: run?.actor_user_id ?? summary.actor_user_id ?? null,
    };
    this.runStatement(
      `INSERT INTO context_summaries
        (id, org_id, actor_user_id, thread_id, run_id, summary, source_message_count, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        stored.id,
        stored.org_id,
        stored.actor_user_id ?? null,
        stored.thread_id,
        stored.run_id,
        stored.summary,
        stored.source_message_count,
        stored.created_at,
      ],
    );
    return stored;
  }

  listContextSummaries(threadId: string, orgId?: string): AgentContextSummary[] {
    const where = orgId ? "thread_id = ? AND org_id = ?" : "thread_id = ?";
    const params = orgId ? [threadId, orgId] : [threadId];
    return this.selectAll<AgentContextSummary>(
      `SELECT * FROM context_summaries
       WHERE ${where}
       ORDER BY created_at ASC`,
      params,
    );
  }

  getLatestContextSummary(threadId: string, orgId?: string): AgentContextSummary | undefined {
    const where = orgId ? "thread_id = ? AND org_id = ?" : "thread_id = ?";
    const params = orgId ? [threadId, orgId] : [threadId];
    return this.selectOne<AgentContextSummary>(
      `SELECT * FROM context_summaries
       WHERE ${where}
       ORDER BY created_at DESC
       LIMIT 1`,
      params,
    );
  }

  setSecret(orgId: string, secretRef: string, value: string): void {
    validateSecretRef(secretRef);
    const existing = this.selectOne<SqliteRow>(
      "SELECT created_at FROM secrets WHERE org_id = ? AND secret_ref = ?",
      [orgId, secretRef],
    );
    const timestamp = nowIso();
    const iv = randomBytes(12);
    const cipher = createCipheriv("aes-256-gcm", this.secretKey, iv);
    const encrypted = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
    const tag = cipher.getAuthTag();
    this.runStatement(
      `INSERT OR REPLACE INTO secrets
        (org_id, secret_ref, encrypted_value, iv, tag, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        orgId,
        secretRef,
        encrypted.toString("base64"),
        iv.toString("base64"),
        tag.toString("base64"),
        typeof existing?.created_at === "string" ? existing.created_at : timestamp,
        timestamp,
      ],
    );
  }

  getSecret(orgId: string, secretRef: string): string | undefined {
    validateSecretRef(secretRef);
    const record = this.selectOne<SqliteRow>(
      "SELECT encrypted_value, iv, tag FROM secrets WHERE org_id = ? AND secret_ref = ?",
      [orgId, secretRef],
    );
    if (
      typeof record?.encrypted_value !== "string" ||
      typeof record.iv !== "string" ||
      typeof record.tag !== "string"
    ) {
      return undefined;
    }
    const decipher = createDecipheriv(
      "aes-256-gcm",
      this.secretKey,
      Buffer.from(record.iv, "base64"),
    );
    decipher.setAuthTag(Buffer.from(record.tag, "base64"));
    return Buffer.concat([
      decipher.update(Buffer.from(record.encrypted_value, "base64")),
      decipher.final(),
    ]).toString("utf8");
  }

  setSetting(orgId: string, key: string, value: string): void {
    this.runStatement(
      `INSERT OR REPLACE INTO settings (org_id, key, value, updated_at)
       VALUES (?, ?, ?, ?)`,
      [orgId, key, value, nowIso()],
    );
  }

  getSetting(orgId: string, key: string): string | undefined {
    const row = this.selectOne<SqliteRow>(
      "SELECT value FROM settings WHERE org_id = ? AND key = ?",
      [orgId, key],
    );
    return typeof row?.value === "string" ? row.value : undefined;
  }

  // ── Claim operations ─────────────────────────────────────────────────

  acquireClaim(
    runId: string,
    workerId: string,
    leaseSeconds = 30,
  ): boolean {
    const run = this.getRun(runId);
    if (!run) throw new Error(`Run ${runId} not found`);

    const now = new Date();
    if (run.claim) {
      const expiresAt = new Date(run.claim.lease_expires_at);
      if (expiresAt > now && run.claim.worker_id !== workerId) return false;
    }

    const claimedAt = now.toISOString().replace(/\.\d{3}/, "");
    const leaseExpiresAt = new Date(now.getTime() + leaseSeconds * 1000)
      .toISOString()
      .replace(/\.\d{3}/, "");
    const attempt = run.claim ? run.claim.attempt + 1 : 1;

    this.runStatement(
      `UPDATE runs
       SET claim_worker_id = ?, claim_claimed_at = ?,
           claim_heartbeat_at = ?, claim_lease_expires_at = ?,
           claim_attempt = ?
       WHERE id = ?`,
      [workerId, claimedAt, claimedAt, leaseExpiresAt, attempt, runId],
    );
    return true;
  }

  releaseClaim(runId: string, workerId: string): void {
    this.runStatement(
      `UPDATE runs
       SET claim_worker_id = NULL, claim_claimed_at = NULL,
           claim_heartbeat_at = NULL, claim_lease_expires_at = NULL,
           claim_attempt = NULL
       WHERE id = ? AND claim_worker_id = ?`,
      [runId, workerId],
    );
  }

  findStaleClaims(now = nowIso()): AgentRun[] {
    return this.selectAll<SqliteRow>(
      `SELECT * FROM runs
       WHERE claim_worker_id IS NOT NULL
         AND status IN ('running', 'waiting_approval', 'waiting_subagent')
         AND claim_lease_expires_at <= ?
       ORDER BY started_at ASC`,
      [now],
    ).map((row) => this.hydrateRun(row));
  }

  // ── Lifecycle ────────────────────────────────────────────────────────

  close(): void {
    if (this.closed) return;
    this.persist();
    this.workspaceFiles.close();
    this.sqlite.close();
    this.closed = true;
  }

  export(): Uint8Array {
    return this.sqlite.export();
  }

  private loadSecretKey(): Buffer {
    if (!this.dbPath || this.dbPath === ":memory:") return randomBytes(32);
    const keyPath = `${this.dbPath}.secrets.key`;
    const directory = dirname(keyPath);
    if (directory && directory !== ".") mkdirSync(directory, { recursive: true });
    if (existsSync(keyPath)) return Buffer.from(readFileSync(keyPath, "utf8").trim(), "base64");
    const key = randomBytes(32);
    writeFileSync(keyPath, key.toString("base64"), { mode: 0o600 });
    return key;
  }

  // ── SQL helpers ──────────────────────────────────────────────────────

  private runStatement(sql: string, params: SqliteParam[] = []): number {
    this.sqlite.run(sql, params);
    const changes = this.sqlite.getRowsModified();
    this.persist();
    return changes;
  }

  private selectOne<T>(sql: string, params: SqliteParam[] = []): T | undefined {
    return this.selectAll<T>(sql, params)[0];
  }

  private selectAll<T>(sql: string, params: SqliteParam[] = []): T[] {
    const stmt = this.sqlite.prepare(sql);
    try {
      stmt.bind(params);
      const rows: T[] = [];
      while (stmt.step()) rows.push(stmt.getAsObject() as T);
      return rows;
    } finally {
      stmt.free();
    }
  }

  private updateRow(
    table: string,
    whereSql: string,
    whereParams: SqliteParam[],
    patch: Record<string, unknown>,
    allowedColumns: readonly string[],
  ): void {
    const entries = Object.entries(patch).filter(
      ([key, value]) =>
        allowedColumns.includes(key) && value !== undefined,
    );
    if (entries.length === 0) return;

    const assignments = entries.map(([key]) => `${key} = ?`).join(", ");
    const params = [
      ...entries.map(([, value]) => value as SqliteParam),
      ...whereParams,
    ];
    this.runStatement(
      `UPDATE ${table} SET ${assignments} WHERE ${whereSql}`,
      params,
    );
  }

  private ensureColumn(table: string, column: string, definition: string): void {
    const columns = this.tableInfo(table);
    if (columns.some((row) => row.name === column)) return;
    this.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
  }

  private migrateSettingsOrgScope(): void {
    const columns = this.tableInfo("settings");
    if (this.hasCompositePrimaryKey(columns, ["org_id", "key"])) return;
    const orgExpr = columns.some((row) => row.name === "org_id")
      ? "COALESCE(NULLIF(org_id, ''), 'org_1')"
      : "'org_1'";
    this.exec(`
      CREATE TABLE settings_scoped_migration (
        org_id TEXT NOT NULL DEFAULT '',
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (org_id, key)
      );
      INSERT OR REPLACE INTO settings_scoped_migration (org_id, key, value, updated_at)
        SELECT ${orgExpr}, key, value, updated_at FROM settings;
      DROP TABLE settings;
      ALTER TABLE settings_scoped_migration RENAME TO settings;
    `);
  }

  private migrateSecretsOrgScope(): void {
    const columns = this.tableInfo("secrets");
    if (this.hasCompositePrimaryKey(columns, ["org_id", "secret_ref"])) return;
    const orgExpr = columns.some((row) => row.name === "org_id")
      ? "COALESCE(NULLIF(org_id, ''), 'org_1')"
      : "'org_1'";
    this.exec(`
      CREATE TABLE secrets_scoped_migration (
        org_id TEXT NOT NULL DEFAULT '',
        secret_ref TEXT NOT NULL,
        encrypted_value TEXT NOT NULL,
        iv TEXT NOT NULL,
        tag TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (org_id, secret_ref)
      );
      INSERT OR REPLACE INTO secrets_scoped_migration
        (org_id, secret_ref, encrypted_value, iv, tag, created_at, updated_at)
        SELECT ${orgExpr}, secret_ref, encrypted_value, iv, tag, created_at, updated_at FROM secrets;
      DROP TABLE secrets;
      ALTER TABLE secrets_scoped_migration RENAME TO secrets;
    `);
  }

  private migrateChildEntityIdentity(): void {
    this.ensureColumn("messages", "org_id", "TEXT");
    this.ensureColumn("messages", "actor_user_id", "TEXT");
    this.ensureColumn("events", "org_id", "TEXT");
    this.ensureColumn("events", "actor_user_id", "TEXT");
    this.ensureColumn("todos", "org_id", "TEXT");
    this.ensureColumn("todos", "actor_user_id", "TEXT");
    this.ensureColumn("todos", "thread_id", "TEXT");
    this.ensureColumn("approvals", "org_id", "TEXT");
    this.ensureColumn("approvals", "actor_user_id", "TEXT");
    this.ensureColumn("context_summaries", "actor_user_id", "TEXT");
    this.exec(`
      UPDATE messages
      SET
        org_id = COALESCE(NULLIF(org_id, ''), (SELECT org_id FROM threads WHERE threads.id = messages.thread_id), (SELECT org_id FROM runs WHERE runs.id = messages.run_id)),
        actor_user_id = COALESCE(NULLIF(actor_user_id, ''), (SELECT actor_user_id FROM runs WHERE runs.id = messages.run_id), (SELECT owner_user_id FROM threads WHERE threads.id = messages.thread_id))
      WHERE org_id IS NULL OR org_id = '' OR actor_user_id IS NULL OR actor_user_id = '';

      UPDATE events
      SET
        org_id = COALESCE(NULLIF(org_id, ''), (SELECT org_id FROM runs WHERE runs.id = events.run_id)),
        actor_user_id = COALESCE(NULLIF(actor_user_id, ''), (SELECT actor_user_id FROM runs WHERE runs.id = events.run_id))
      WHERE org_id IS NULL OR org_id = '' OR actor_user_id IS NULL OR actor_user_id = '';

      UPDATE todos
      SET
        org_id = COALESCE(NULLIF(org_id, ''), (SELECT org_id FROM runs WHERE runs.id = todos.run_id)),
        actor_user_id = COALESCE(NULLIF(actor_user_id, ''), (SELECT actor_user_id FROM runs WHERE runs.id = todos.run_id)),
        thread_id = COALESCE(thread_id, (SELECT thread_id FROM runs WHERE runs.id = todos.run_id))
      WHERE org_id IS NULL OR org_id = '' OR actor_user_id IS NULL OR actor_user_id = '' OR thread_id IS NULL;

      UPDATE approvals
      SET
        org_id = COALESCE(NULLIF(org_id, ''), (SELECT org_id FROM runs WHERE runs.id = approvals.run_id)),
        actor_user_id = COALESCE(NULLIF(actor_user_id, ''), (SELECT actor_user_id FROM runs WHERE runs.id = approvals.run_id))
      WHERE org_id IS NULL OR org_id = '' OR actor_user_id IS NULL OR actor_user_id = '';

      UPDATE context_summaries
      SET actor_user_id = COALESCE(NULLIF(actor_user_id, ''), (SELECT actor_user_id FROM runs WHERE runs.id = context_summaries.run_id))
      WHERE actor_user_id IS NULL OR actor_user_id = '';

      CREATE INDEX IF NOT EXISTS idx_todos_thread ON todos(thread_id);
      CREATE INDEX IF NOT EXISTS idx_messages_org_thread ON messages(org_id, thread_id);
      CREATE INDEX IF NOT EXISTS idx_events_org_run ON events(org_id, run_id);
      CREATE INDEX IF NOT EXISTS idx_todos_org_run ON todos(org_id, run_id);
      CREATE INDEX IF NOT EXISTS idx_approvals_org_run ON approvals(org_id, run_id);
      CREATE INDEX IF NOT EXISTS idx_context_summaries_org_thread
        ON context_summaries(org_id, thread_id, created_at);
    `);
  }

  private tableInfo(table: string): SqliteRow[] {
    return this.selectAll<SqliteRow>(`PRAGMA table_info(${table})`);
  }

  private hasCompositePrimaryKey(columns: SqliteRow[], names: string[]): boolean {
    const pk = columns
      .filter((row) => Number(row.pk ?? 0) > 0)
      .sort((a, b) => Number(a.pk) - Number(b.pk))
      .map((row) => String(row.name));
    return pk.length === names.length && pk.every((name, index) => name === names[index]);
  }

  private hydrateMessage(row: SqliteRow): AgentMessage {
    return {
      id: String(row.id),
      org_id: row.org_id == null ? null : String(row.org_id),
      actor_user_id: row.actor_user_id == null ? null : String(row.actor_user_id),
      thread_id: String(row.thread_id),
      role: row.role as AgentMessage["role"],
      content: String(row.content),
      run_id: row.run_id == null ? null : String(row.run_id),
      workspace_paths: parseJson<string[]>(row.workspace_paths, []),
      created_at: String(row.created_at),
    };
  }

  private hydrateRun(row: SqliteRow): AgentRun {
    const run: AgentRun = {
      id: String(row.id),
      org_id: String(row.org_id),
      actor_user_id: String(row.actor_user_id),
      source: row.source as AgentRun["source"],
      thread_id: row.thread_id == null ? null : String(row.thread_id),
      workspace_id: String(row.workspace_id),
      task_msg: String(row.task_msg),
      scopes: parseJson<string[]>(row.scopes, []),
      harness_options: parseJson(row.harness_options, null),
      status: row.status as AgentRun["status"],
      current_approval_id:
        row.current_approval_id == null
          ? null
          : String(row.current_approval_id),
      started_at: String(row.started_at),
      completed_at:
        row.completed_at == null ? null : String(row.completed_at),
      claim:
        row.claim_worker_id == null
          ? null
          : {
              worker_id: String(row.claim_worker_id),
              claimed_at: String(row.claim_claimed_at),
              last_heartbeat_at:
                row.claim_heartbeat_at == null
                  ? null
                  : String(row.claim_heartbeat_at),
              lease_expires_at: String(row.claim_lease_expires_at),
              attempt: Number(row.claim_attempt ?? 1),
            },
      result: parseJson(row.result, null),
      error: parseJson(row.error, null),
    };

    if (row.retry_policy != null)
      (run as any).retry_policy = parseJson(row.retry_policy, null);
    if (row.retry_state != null)
      (run as any).retry_state = parseJson(row.retry_state, null);
    return run;
  }

  private hydrateEvent(row: SqliteRow): AgentStreamEvent {
    return {
      id: String(row.id),
      org_id: row.org_id == null ? null : String(row.org_id),
      actor_user_id: row.actor_user_id == null ? null : String(row.actor_user_id),
      run_id: String(row.run_id),
      thread_id: row.thread_id == null ? null : String(row.thread_id),
      sequence: Number(row.sequence),
      timestamp: String(row.timestamp),
      type: String(row.type),
      source: {
        kind: String(row.source_kind),
        id: row.source_id == null ? null : String(row.source_id),
        name: row.source_name == null ? null : String(row.source_name),
      },
      visibility: row.visibility as AgentStreamEvent["visibility"],
      redaction: row.redaction as AgentStreamEvent["redaction"],
      summary: row.summary == null ? null : String(row.summary),
      payload: parseJson(row.payload, {}),
    };
  }

  private persist(): void {
    if (!this.dbPath || this.dbPath === ":memory:" || this.closed) return;
    const directory = dirname(this.dbPath);
    if (directory && directory !== ".") mkdirSync(directory, { recursive: true });
    writeFileSync(this.dbPath, Buffer.from(this.sqlite.export()));
  }

  private documentTable(kind: string): string | undefined {
    return DOCUMENT_TABLES[kind as DocumentKind];
  }

  private setVolatileDocument(kind: string, id: string, payload: unknown): void {
    const docs = this.volatileDocuments.get(kind) ?? new Map<string, unknown>();
    docs.set(id, payload);
    this.volatileDocuments.set(kind, docs);
  }

  private getVolatileDocument(kind: string, id: string): AgentDocument | undefined {
    const docs = this.volatileDocuments.get(kind);
    if (!docs?.has(id)) return undefined;
    return { kind, id, payload: docs.get(id) };
  }

  private listVolatileDocuments(kind: string, orgId: string): AgentDocument[] {
    return [...(this.volatileDocuments.get(kind) ?? new Map<string, unknown>()).entries()]
      .filter(([, payload]) => documentFields(payload).orgId === orgId)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([id, payload]) => ({ kind, id, payload }));
  }

  private deleteVolatileDocument(kind: string, id: string, guard?: DocumentWriteGuard): number {
    const docs = this.volatileDocuments.get(kind);
    const existing = docs?.get(id);
    if (existing === undefined || !documentMatchesGuard(existing, guard)) return 0;
    return docs!.delete(id) ? 1 : 0;
  }

  private todoScope(runId: string): { column: string; value: string; orgId: string } {
    const run = this.getRun(runId);
    const threadId = run?.thread_id ?? null;
    return threadId
      ? { column: "thread_id", value: threadId, orgId: run?.org_id ?? "org_1" }
      : { column: "run_id", value: runId, orgId: run?.org_id ?? "org_1" };
  }
}

function documentFields(payload: unknown): {
  orgId: string | null;
  ownerUserId: string | null;
  key: string | null;
} {
  const record = payload && typeof payload === "object"
    ? (payload as Record<string, unknown>)
    : {};
  return {
    orgId: typeof record.org_id === "string" ? record.org_id : null,
    ownerUserId: typeof record.owner_user_id === "string" ? record.owner_user_id : null,
    key: typeof record.key === "string" ? record.key : null,
  };
}

function documentMatchesGuard(payload: unknown, guard?: DocumentWriteGuard): boolean {
  if (!guard) return true;
  const fields = documentFields(payload);
  if (guard.orgId && fields.orgId !== guard.orgId) return false;
  if (guard.ownerUserId && fields.ownerUserId !== guard.ownerUserId) return false;
  return true;
}
