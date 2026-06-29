import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import initSqlJs, { type Database as SqlJsDatabase } from "sql.js";
import type { AgentStore } from "./protocols.js";
import type {
  AgentThread,
  AgentMessage,
  AgentRun,
  AgentStreamEvent,
} from "../contracts/types.js";
import type {
  WorkspaceFile,
  AgentTodo,
  AgentApproval,
  AgentArtifact,
} from "./store.js";
import { runMigrations } from "./migrations.js";

type SqliteParam = string | number | null;
type SqliteRow = Record<string, unknown>;

const RUN_COLUMNS = [
  "org_id",
  "actor_user_id",
  "source",
  "thread_id",
  "skill_id",
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

export class SqliteStore implements AgentStore {
  private closed = false;

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
    store.persist();
    return store;
  }

  private constructor(
    private sqlite: SqlJsDatabase,
    private dbPath?: string,
  ) {}

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
    this.runStatement(
      `INSERT INTO messages
        (id, thread_id, role, content, run_id, workspace_paths, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        msg.id,
        msg.thread_id,
        String(msg.role),
        msg.content,
        msg.run_id ?? null,
        JSON.stringify(msg.workspace_paths),
        msg.created_at,
      ],
    );
    return msg;
  }

  getMessage(id: string): AgentMessage | undefined {
    const row = this.selectOne<SqliteRow>(
      "SELECT * FROM messages WHERE id = ?",
      [id],
    );
    return row ? this.hydrateMessage(row) : undefined;
  }

  listMessages(threadId: string): AgentMessage[] {
    return this.selectAll<SqliteRow>(
      "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
      [threadId],
    ).map((row) => this.hydrateMessage(row));
  }

  // ── Runs ─────────────────────────────────────────────────────────────

  createRun(run: AgentRun): AgentRun {
    this.runStatement(
      `INSERT INTO runs
        (id, org_id, actor_user_id, source, thread_id, skill_id, workspace_id,
         task_msg, scopes, harness_options, status, started_at, completed_at,
         current_approval_id, claim_worker_id, claim_claimed_at,
         claim_heartbeat_at, claim_lease_expires_at, claim_attempt,
         retry_policy, retry_state, result, error)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        run.id,
        run.org_id,
        run.actor_user_id,
        String(run.source),
        run.thread_id ?? null,
        run.skill_id ?? null,
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
    this.runStatement(
      `INSERT INTO events
        (id, run_id, thread_id, sequence, timestamp, type, source_kind,
         source_id, source_name, visibility, redaction, summary, payload)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        event.id,
        runId,
        event.thread_id ?? null,
        event.sequence,
        event.timestamp,
        event.type,
        event.source.kind,
        event.source.id ?? null,
        event.source.name ?? null,
        event.visibility,
        event.redaction,
        event.summary ?? null,
        JSON.stringify(event.payload),
      ],
    );
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
  ): WorkspaceFile {
    const existing = this.readFile(workspaceId, path);
    const timestamp = nowIso();

    if (existing) {
      this.runStatement(
        `UPDATE workspace_files
         SET content = ?, size = ?, version = ?, updated_at = ?
         WHERE workspace_id = ? AND path = ?`,
        [
          content,
          Buffer.byteLength(content, "utf8"),
          existing.version + 1,
          timestamp,
          workspaceId,
          path,
        ],
      );
      return this.readFile(workspaceId, path)!;
    }

    const file: WorkspaceFile = {
      workspace_id: workspaceId,
      path,
      content,
      size: Buffer.byteLength(content, "utf8"),
      version: 1,
      created_at: timestamp,
      updated_at: timestamp,
    };
    this.runStatement(
      `INSERT INTO workspace_files
        (workspace_id, path, content, size, version, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        file.workspace_id,
        file.path,
        file.content,
        file.size,
        file.version,
        file.created_at,
        file.updated_at,
      ],
    );
    return file;
  }

  readFile(workspaceId: string, path: string): WorkspaceFile | undefined {
    return this.selectOne<WorkspaceFile>(
      "SELECT * FROM workspace_files WHERE workspace_id = ? AND path = ?",
      [workspaceId, path],
    );
  }

  listWorkspaceFiles(workspaceId: string): WorkspaceFile[] {
    return this.selectAll<WorkspaceFile>(
      "SELECT * FROM workspace_files WHERE workspace_id = ? ORDER BY path ASC",
      [workspaceId],
    );
  }

  deleteFile(workspaceId: string, path: string): boolean {
    return (
      this.runStatement(
        "DELETE FROM workspace_files WHERE workspace_id = ? AND path = ?",
        [workspaceId, path],
      ) > 0
    );
  }

  // ── Todos ────────────────────────────────────────────────────────────

  createTodo(todo: AgentTodo): AgentTodo {
    this.runStatement(
      `INSERT INTO todos
        (id, run_id, title, status, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [
        todo.id,
        todo.run_id,
        todo.title,
        todo.status,
        todo.created_at,
        todo.updated_at,
      ],
    );
    return todo;
  }

  updateTodo(
    runId: string,
    todoId: string,
    patch: Partial<AgentTodo>,
  ): AgentTodo {
    this.updateRow("todos", "id = ? AND run_id = ?", [todoId, runId], {
      ...patch,
      updated_at: nowIso(),
    }, ["title", "status", "created_at", "updated_at"]);
    const todo = this.selectOne<AgentTodo>(
      "SELECT * FROM todos WHERE id = ? AND run_id = ?",
      [todoId, runId],
    );
    if (!todo) throw new Error(`Todo ${todoId} not found`);
    return todo;
  }

  listTodos(runId: string): AgentTodo[] {
    return this.selectAll<AgentTodo>(
      "SELECT * FROM todos WHERE run_id = ? ORDER BY created_at ASC",
      [runId],
    );
  }

  // ── Approvals ────────────────────────────────────────────────────────

  createApproval(approval: AgentApproval): AgentApproval {
    this.runStatement(
      `INSERT INTO approvals
        (id, run_id, tool_call_id, tool_name, status, created_at, resolved_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        approval.id,
        approval.run_id,
        approval.tool_call_id,
        approval.tool_name,
        approval.status,
        approval.created_at,
        approval.resolved_at ?? null,
      ],
    );
    return approval;
  }

  getApproval(id: string): AgentApproval | undefined {
    return this.selectOne<AgentApproval>(
      "SELECT * FROM approvals WHERE id = ?",
      [id],
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

  // ── Artifacts ────────────────────────────────────────────────────────

  createArtifact(artifact: AgentArtifact): AgentArtifact {
    this.runStatement(
      `INSERT INTO artifacts
        (id, run_id, title, content_type, content, status, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        artifact.id,
        artifact.run_id,
        artifact.title,
        artifact.content_type,
        artifact.content,
        artifact.status,
        artifact.created_at,
        artifact.updated_at,
      ],
    );
    return artifact;
  }

  getArtifact(id: string): AgentArtifact | undefined {
    return this.selectOne<AgentArtifact>(
      "SELECT * FROM artifacts WHERE id = ?",
      [id],
    );
  }

  listArtifacts(runId: string): AgentArtifact[] {
    return this.selectAll<AgentArtifact>(
      "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at ASC",
      [runId],
    );
  }

  finalizeArtifact(id: string): AgentArtifact {
    this.runStatement(
      "UPDATE artifacts SET status = ?, updated_at = ? WHERE id = ?",
      ["finalized", nowIso(), id],
    );
    const artifact = this.getArtifact(id);
    if (!artifact) throw new Error(`Artifact ${id} not found`);
    return artifact;
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
    this.sqlite.close();
    this.closed = true;
  }

  export(): Uint8Array {
    return this.sqlite.export();
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

  private hydrateMessage(row: SqliteRow): AgentMessage {
    return {
      id: String(row.id),
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
      skill_id: row.skill_id == null ? null : String(row.skill_id),
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
}
