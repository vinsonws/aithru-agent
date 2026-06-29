import initSqlJs from "sql.js";
import { Kysely, SqliteDialect } from "kysely";
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
import { SqlJsToKyselyAdapter } from "./sqljs-wrapper.js";

export class SqliteStore implements AgentStore {
  private db: Kysely<any>;
  private adapter: SqlJsToKyselyAdapter;
  private closed = false;

  /**
   * Create and initialise a SqliteStore.
   *
   * Uses sql.js (WASM) under the hood so there is no native compilation
   * requirement.  The optional `buffer` param allows loading / restoring
   * a previously-serialised database (`sqlite.export()`).
   */
  static async create(buffer?: Uint8Array): Promise<SqliteStore> {
    const SQL = await initSqlJs();
    const sqlite = new SQL.Database(buffer ?? undefined);
    const adapter = new SqlJsToKyselyAdapter(sqlite);
    const db = new Kysely<any>({
      dialect: new SqliteDialect({ database: adapter as any }),
    });
    runMigrations(adapter);
    return new SqliteStore(db, adapter);
  }

  private constructor(db: Kysely<any>, adapter: SqlJsToKyselyAdapter) {
    this.db = db;
    this.adapter = adapter;
  }

  // ── Threads ──────────────────────────────────────────────────────────

  createThread(thread: AgentThread): AgentThread {
    this.db.insertInto("threads").values(thread as any).execute();
    return thread;
  }

  getThread(id: string): AgentThread | undefined {
    return this.db
      .selectFrom("threads")
      .selectAll()
      .where("id", "=", id)
      .executeTakeFirst() as any;
  }

  listThreads(orgId?: string): AgentThread[] {
    let q = this.db.selectFrom("threads").selectAll();
    if (orgId) q = q.where("org_id", "=", orgId);
    return q.execute() as any;
  }

  updateThread(id: string, patch: Partial<AgentThread>): AgentThread {
    this.db
      .updateTable("threads")
      .set(patch as any)
      .where("id", "=", id)
      .execute();
    return this.getThread(id)!;
  }

  // ── Messages ─────────────────────────────────────────────────────────

  createMessage(msg: AgentMessage): AgentMessage {
    this.db
      .insertInto("messages")
      .values({
        ...msg,
        workspace_paths: JSON.stringify(msg.workspace_paths),
      } as any)
      .execute();
    return msg;
  }

  getMessage(id: string): AgentMessage | undefined {
    const row = this.db
      .selectFrom("messages")
      .selectAll()
      .where("id", "=", id)
      .executeTakeFirst() as any;
    if (!row) return undefined;
    return { ...row, workspace_paths: JSON.parse(row.workspace_paths) };
  }

  listMessages(threadId: string): AgentMessage[] {
    return (
      this.db
        .selectFrom("messages")
        .selectAll()
        .where("thread_id", "=", threadId)
        .orderBy("created_at", "asc")
        .execute() as unknown as any[]
    ).map((r: any) => ({
      ...r,
      workspace_paths: JSON.parse(r.workspace_paths),
    }));
  }

  // ── Runs ─────────────────────────────────────────────────────────────

  createRun(run: AgentRun): AgentRun {
    this.db
      .insertInto("runs")
      .values({
        ...run,
        scopes: JSON.stringify(run.scopes),
        harness_options: run.harness_options
          ? JSON.stringify(run.harness_options)
          : null,
        claim_worker_id: run.claim?.worker_id ?? null,
        claim_claimed_at: run.claim?.claimed_at ?? null,
        claim_heartbeat_at: run.claim?.last_heartbeat_at ?? null,
        claim_lease_expires_at: run.claim?.lease_expires_at ?? null,
        claim_attempt: run.claim?.attempt ?? null,
        result: run.result ? JSON.stringify(run.result) : null,
        error: run.error ? JSON.stringify(run.error) : null,
      } as any)
      .execute();
    return run;
  }

  getRun(id: string): AgentRun | undefined {
    const row = this.db
      .selectFrom("runs")
      .selectAll()
      .where("id", "=", id)
      .executeTakeFirst() as any;
    return row ? this._hydrateRun(row) : undefined;
  }

  listRuns(filter?: { org_id?: string; thread_id?: string }): AgentRun[] {
    let q = this.db.selectFrom("runs").selectAll();
    if (filter?.org_id) q = q.where("org_id", "=", filter.org_id);
    if (filter?.thread_id)
      q = q.where("thread_id", "=", filter.thread_id);
    return (q.execute() as unknown as any[]).map((r: any) => this._hydrateRun(r));
  }

  updateRun(id: string, patch: Partial<AgentRun>): AgentRun {
    const flat: any = { ...patch };
    if (patch.scopes) flat.scopes = JSON.stringify(patch.scopes);
    if (patch.result) flat.result = JSON.stringify(patch.result);
    if (patch.error) flat.error = JSON.stringify(patch.error);
    if (patch.harness_options)
      flat.harness_options = JSON.stringify(patch.harness_options);
    if (patch.claim) {
      flat.claim_worker_id = patch.claim.worker_id;
      flat.claim_claimed_at = patch.claim.claimed_at;
      flat.claim_heartbeat_at = patch.claim.last_heartbeat_at ?? null;
      flat.claim_lease_expires_at = patch.claim.lease_expires_at;
      flat.claim_attempt = patch.claim.attempt;
    }
    delete flat.claim;
    // harness_options already handled above
    this.db.updateTable("runs").set(flat).where("id", "=", id).execute();
    return this.getRun(id)!;
  }

  private _hydrateRun(row: any): AgentRun {
    const run: any = {
      ...row,
      scopes: JSON.parse(row.scopes || "[]"),
    };
    if (row.harness_options)
      run.harness_options = JSON.parse(row.harness_options);
    if (row.claim_worker_id) {
      run.claim = {
        worker_id: row.claim_worker_id,
        claimed_at: row.claim_claimed_at,
        last_heartbeat_at: row.claim_heartbeat_at,
        lease_expires_at: row.claim_lease_expires_at,
        attempt: row.claim_attempt,
      };
    }
    if (row.result) run.result = JSON.parse(row.result);
    if (row.error) run.error = JSON.parse(row.error);
    if (row.retry_policy) run.retry_policy = JSON.parse(row.retry_policy);
    if (row.retry_state) run.retry_state = JSON.parse(row.retry_state);
    return run;
  }

  // ── Events ───────────────────────────────────────────────────────────

  appendEvent(runId: string, event: AgentStreamEvent): void {
    this.db
      .insertInto("events")
      .values({
        ...event,
        source_kind: event.source.kind,
        source_id: event.source.id ?? null,
        source_name: event.source.name ?? null,
        payload: JSON.stringify(event.payload),
      } as any)
      .execute();
  }

  listEvents(runId: string): AgentStreamEvent[] {
    return (
      this.db
        .selectFrom("events")
        .selectAll()
        .where("run_id", "=", runId)
        .orderBy("sequence", "asc")
        .execute() as unknown as any[]
    ).map((r: any) => ({
      ...r,
      source: { kind: r.source_kind, id: r.source_id, name: r.source_name },
      payload: JSON.parse(r.payload),
    }));
  }

  // ── Workspace ────────────────────────────────────────────────────────

  writeFile(
    workspaceId: string,
    path: string,
    content: string,
  ): WorkspaceFile {
    const now = new Date().toISOString().replace(/\.\d{3}/, "");
    const existing = this.db
      .selectFrom("workspace_files")
      .selectAll()
      .where("workspace_id", "=", workspaceId)
      .where("path", "=", path)
      .executeTakeFirst() as any;

    if (existing) {
      this.db
        .updateTable("workspace_files")
        .set({
          content,
          size: Buffer.byteLength(content, "utf8"),
          version: existing.version + 1,
          updated_at: now,
        } as any)
        .where("workspace_id", "=", workspaceId)
        .where("path", "=", path)
        .execute();
      return {
        ...existing,
        content,
        version: existing.version + 1,
        updated_at: now,
      };
    }

    const file: WorkspaceFile = {
      workspace_id: workspaceId,
      path,
      content,
      size: Buffer.byteLength(content, "utf8"),
      version: 1,
      created_at: now,
      updated_at: now,
    };
    this.db
      .insertInto("workspace_files")
      .values(file as any)
      .execute();
    return file;
  }

  readFile(wsId: string, path: string): WorkspaceFile | undefined {
    return this.db
      .selectFrom("workspace_files")
      .selectAll()
      .where("workspace_id", "=", wsId)
      .where("path", "=", path)
      .executeTakeFirst() as any;
  }

  listWorkspaceFiles(wsId: string): WorkspaceFile[] {
    return this.db
      .selectFrom("workspace_files")
      .selectAll()
      .where("workspace_id", "=", wsId)
      .execute() as any;
  }

  deleteFile(wsId: string, path: string): boolean {
    const r = this.db
      .deleteFrom("workspace_files")
      .where("workspace_id", "=", wsId)
      .where("path", "=", path)
      .execute();
    // Kysely's execute() returns the result rows array; we check if any were
    // affected by re-checking.
    const after = this.db
      .selectFrom("workspace_files")
      .selectAll()
      .where("workspace_id", "=", wsId)
      .where("path", "=", path)
      .executeTakeFirst();
    return !after;
  }

  // ── Todos ────────────────────────────────────────────────────────────

  createTodo(todo: AgentTodo): AgentTodo {
    this.db.insertInto("todos").values(todo as any).execute();
    return todo;
  }

  updateTodo(
    runId: string,
    todoId: string,
    patch: Partial<AgentTodo>,
  ): AgentTodo {
    this.db
      .updateTable("todos")
      .set({
        ...patch,
        updated_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      } as any)
      .where("id", "=", todoId)
      .execute();
    return this.db
      .selectFrom("todos")
      .selectAll()
      .where("id", "=", todoId)
      .executeTakeFirst() as any;
  }

  listTodos(runId: string): AgentTodo[] {
    return this.db
      .selectFrom("todos")
      .selectAll()
      .where("run_id", "=", runId)
      .execute() as any;
  }

  // ── Approvals ────────────────────────────────────────────────────────

  createApproval(a: AgentApproval): AgentApproval {
    this.db.insertInto("approvals").values(a as any).execute();
    return a;
  }

  getApproval(id: string): AgentApproval | undefined {
    return this.db
      .selectFrom("approvals")
      .selectAll()
      .where("id", "=", id)
      .executeTakeFirst() as any;
  }

  resolveApproval(
    id: string,
    status: "approved" | "denied",
  ): AgentApproval {
    this.db
      .updateTable("approvals")
      .set({
        status,
        resolved_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      } as any)
      .where("id", "=", id)
      .execute();
    return this.getApproval(id)!;
  }

  // ── Artifacts ────────────────────────────────────────────────────────

  createArtifact(a: AgentArtifact): AgentArtifact {
    this.db.insertInto("artifacts").values(a as any).execute();
    return a;
  }

  getArtifact(id: string): AgentArtifact | undefined {
    return this.db
      .selectFrom("artifacts")
      .selectAll()
      .where("id", "=", id)
      .executeTakeFirst() as any;
  }

  listArtifacts(runId: string): AgentArtifact[] {
    return this.db
      .selectFrom("artifacts")
      .selectAll()
      .where("run_id", "=", runId)
      .execute() as any;
  }

  finalizeArtifact(id: string): AgentArtifact {
    this.db
      .updateTable("artifacts")
      .set({
        status: "finalized",
        updated_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      } as any)
      .where("id", "=", id)
      .execute();
    return this.getArtifact(id)!;
  }

  // ── Claim operations ─────────────────────────────────────────────────

  acquireClaim(
    runId: string,
    workerId: string,
    leaseSeconds = 300,
  ): boolean {
    const now = new Date().toISOString().replace(/\.\d{3}/, "");
    const expires = new Date(Date.now() + leaseSeconds * 1000)
      .toISOString()
      .replace(/\.\d{3}/, "");

    // Only acquire if no active unexpired claim exists.
    // Kysely's dynamic where with eb.or()
    const result = this.db
      .updateTable("runs")
      .set({
        claim_worker_id: workerId,
        claim_claimed_at: now,
        claim_lease_expires_at: expires,
      } as any)
      .where("id", "=", runId)
      .where((eb) =>
        eb.or([
          eb("claim_worker_id", "is", null),
          eb("claim_lease_expires_at", "<=", now),
        ]),
      )
      .execute();

    // Check if any row was updated by querying the run.
    const updated = this.getRun(runId);
    return updated?.claim?.worker_id === workerId;
  }

  renewClaim(
    runId: string,
    workerId: string,
    leaseSeconds = 300,
  ): boolean {
    const now = new Date().toISOString().replace(/\.\d{3}/, "");
    const expires = new Date(Date.now() + leaseSeconds * 1000)
      .toISOString()
      .replace(/\.\d{3}/, "");

    const result = this.db
      .updateTable("runs")
      .set({
        claim_heartbeat_at: now,
        claim_lease_expires_at: expires,
      } as any)
      .where("id", "=", runId)
      .where("claim_worker_id", "=", workerId)
      .execute();
    return (result as any).length > 0;
  }

  releaseClaim(runId: string, workerId: string): void {
    this.db
      .updateTable("runs")
      .set({
        claim_worker_id: null,
        claim_claimed_at: null,
        claim_heartbeat_at: null,
        claim_lease_expires_at: null,
      } as any)
      .where("id", "=", runId)
      .where("claim_worker_id", "=", workerId)
      .execute();
  }

  findStaleClaims(now?: string): AgentRun[] {
    const ts =
      now || new Date().toISOString().replace(/\.\d{3}/, "");
    return (
      this.db
        .selectFrom("runs")
        .selectAll()
        .where("status", "in", [
          "running",
          "waiting_approval",
          "waiting_subagent",
        ])
        .where("claim_lease_expires_at", "<=", ts)
        .execute() as unknown as any[]
    ).map((r: any) => this._hydrateRun(r));
  }

  // ── Lifecycle ────────────────────────────────────────────────────────

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.adapter.close();
  }

  /**
   * Export the current database as a Uint8Array for persistence
   * (sql.js stores everything in memory by default).
   */
  export(): Uint8Array {
    return this.adapter.raw().export();
  }
}
