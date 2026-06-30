import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import initSqlJs from "sql.js";
import { SqliteStore } from "@aithru-agent/persistence";

describe("SqliteStore", () => {
  let store: SqliteStore;
  let tempDir: string;

  beforeEach(async () => {
    tempDir = mkdtempSync(join(tmpdir(), "aithru-sqlite-"));
    store = await SqliteStore.create();
  });

  afterEach(() => {
    store.close();
    rmSync(tempDir, { recursive: true, force: true });
  });

  it("creates and retrieves a thread", () => {
    const thread = {
      id: "t1",
      org_id: "o1",
      owner_user_id: "u1",
      title: "Test",
      status: "active" as const,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    store.createThread(thread);
    expect(store.getThread("t1")).toEqual(thread);
  });

  it("persists data to a dbPath and reloads it", async () => {
    const dbPath = join(tempDir, "agent.sqlite");
    const durable = await SqliteStore.create(dbPath);
    durable.createThread({
      id: "persisted",
      org_id: "o1",
      owner_user_id: "u1",
      title: "Durable",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    durable.close();

    const reopened = await SqliteStore.create(dbPath);
    try {
      expect(reopened.getThread("persisted")?.title).toBe("Durable");
    } finally {
      reopened.close();
    }
  });

  it("opens an existing db whose todos table predates thread_id", async () => {
    const dbPath = join(tempDir, "legacy.sqlite");
    const SQL = await initSqlJs();
    const legacy = new SQL.Database();
    legacy.run(`
      CREATE TABLE todos (
        id TEXT PRIMARY KEY, run_id TEXT NOT NULL, title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      );
    `);
    legacy.run(
      `INSERT INTO todos (id, run_id, title, status, created_at, updated_at)
       VALUES ('todo_legacy', 'run_legacy', 'Legacy todo', 'pending', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')`,
    );
    writeFileSync(dbPath, Buffer.from(legacy.export()));
    legacy.close();

    const reopened = await SqliteStore.create(dbPath);
    try {
      const raw = new SQL.Database(readFileSync(dbPath));
      try {
        const columns = raw.exec("PRAGMA table_info(todos)");
        expect(columns[0]?.values.map((column) => column[1])).toContain("thread_id");
      } finally {
        raw.close();
      }
      expect(reopened.listTodos("run_legacy")).toHaveLength(1);
    } finally {
      reopened.close();
    }
  });

  it("persists settings, dedicated config docs, and encrypted secrets outside agent_documents", async () => {
    const dbPath = join(tempDir, "settings.sqlite");
    const secretRef = "secret://model-profiles/org_1/deepseek-v4-flash/api-key";
    const durable = await SqliteStore.create(dbPath);
    durable.setSetting("model.default_profile_id", "profile_1");
    durable.upsertDocument("model_profile_entry", "profile_1", {
      id: "profile_1",
      org_id: "org_1",
      key: "deepseek-v4-flash",
      provider: "deepseek",
      model: "DeepSeekv4 flash",
      auth_secret: { secret_ref: secretRef, status: "set" },
    });
    durable.setSecret(secretRef, "sk-test-secret");
    durable.writeFile("ws1", "/notes.txt", "one");
    expect(durable.readFile("ws1", "/notes.txt")?.content).toBe("one");
    durable.close();

    const reopened = await SqliteStore.create(dbPath);
    try {
      expect(reopened.getSetting("model.default_profile_id")).toBe("profile_1");
      expect(reopened.getDocument("model_profile_entry", "profile_1")?.payload).toMatchObject({
        key: "deepseek-v4-flash",
        auth_secret: { secret_ref: secretRef, status: "set" },
      });
      expect(reopened.getSecret(secretRef)).toBe("sk-test-secret");
      expect(reopened.readFile("ws1", "/notes.txt")).toBeUndefined();
    } finally {
      reopened.close();
    }

    const SQL = await initSqlJs();
    const raw = new SQL.Database(readFileSync(dbPath));
    try {
      const tableRows = raw.exec("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name");
      const tables = tableRows[0]?.values.map(([name]) => String(name)) ?? [];
      expect(tables).toEqual(expect.arrayContaining(["settings", "secrets", "model_profiles"]));
      expect(tables).not.toContain("agent_documents");
      expect(tables).not.toContain("workspace_files");
      expect(tables).not.toContain("workspace_file_versions");

      const secretRows = raw.exec(`SELECT encrypted_value FROM secrets WHERE secret_ref = '${secretRef}'`);
      expect(secretRows[0]?.values).toHaveLength(1);
      expect(String(secretRows[0].values[0][0])).not.toContain("sk-test-secret");
    } finally {
      raw.close();
    }
  });

  it("persists context summaries outside agent_documents", async () => {
    const dbPath = join(tempDir, "context-summary.sqlite");
    const durable = await SqliteStore.create(dbPath);
    durable.createContextSummary({
      id: "summary_1",
      org_id: "org_1",
      thread_id: "thread_1",
      run_id: "run_1",
      summary: "Older conversation summary.",
      source_message_count: 14,
      created_at: "2026-01-01T00:00:00Z",
    });
    durable.close();

    const reopened = await SqliteStore.create(dbPath);
    try {
      expect(reopened.getLatestContextSummary("thread_1")?.summary).toBe(
        "Older conversation summary.",
      );
    } finally {
      reopened.close();
    }
  });

  it("acquires and releases claims", () => {
    const run = {
      id: "r1",
      org_id: "o1",
      actor_user_id: "u1",
      source: "api" as const,
      thread_id: null,
      workspace_id: "w1",
      task_msg: "test",
      scopes: [] as string[],
      harness_options: null,
      status: "queued" as const,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      current_approval_id: null,
      claim: null,
      result: null,
      error: null,
    };
    store.createRun(run);
    expect(store.acquireClaim("r1", "w1")).toBe(true);
    expect(store.acquireClaim("r1", "w2")).toBe(false);
    store.releaseClaim("r1", "w1");
    expect(store.acquireClaim("r1", "w2")).toBe(true);
  });

  it("finds stale claims", () => {
    const run = {
      id: "r2",
      org_id: "o1",
      actor_user_id: "u1",
      source: "api" as const,
      thread_id: null,
      workspace_id: "w2",
      task_msg: "test",
      scopes: ["*"],
      harness_options: null,
      status: "running" as const,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      current_approval_id: null,
      claim: null,
      result: null,
      error: null,
    };
    store.createRun(run);
    const pastTime = new Date(Date.now() - 100000)
      .toISOString()
      .replace(/\.\d{3}/, "");
    store.updateRun("r2", {
      claim: {
        worker_id: "dead",
        claimed_at: pastTime,
        last_heartbeat_at: null,
        lease_expires_at: pastTime,
        attempt: 1,
      },
    } as any);
    const stale = store.findStaleClaims();
    expect(stale.map((staleRun) => staleRun.id)).toContain("r2");
  });

  it("creates and retrieves a run", () => {
    const run = {
      id: "r3",
      org_id: "o1",
      actor_user_id: "u1",
      source: "api" as const,
      thread_id: null,
      workspace_id: "w3",
      task_msg: "Hello",
      scopes: ["*"],
      harness_options: null,
      status: "queued" as const,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      current_approval_id: null,
      claim: null,
      result: null,
      error: null,
    };
    store.createRun(run);
    const got = store.getRun("r3");
    expect(got).toBeDefined();
    expect(got!.task_msg).toBe("Hello");
    expect(got!.status).toBe("queued");
  });

  it("stores runs without a skill_id column", async () => {
    const localStore = await SqliteStore.create(":memory:");
    const run = localStore.createRun({
      id: "run_no_skill_id",
      org_id: "org_1",
      actor_user_id: "user_1",
      source: "chat",
      thread_id: null,
      workspace_id: "ws_1",
      task_msg: "hello",
      scopes: ["*"],
      harness_options: null,
      status: "queued",
      current_approval_id: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      claim: null,
      result: null,
      error: null,
    });

    expect("skill_id" in run).toBe(false);
    expect("skill_id" in localStore.getRun("run_no_skill_id")!).toBe(false);
    localStore.close();
  });

  it("writes and reads workspace files", () => {
    const file = store.writeFile("ws1", "/test.txt", "hello");
    expect(file.path).toBe("/test.txt");
    expect(file.content).toBe("hello");
    const read = store.readFile("ws1", "/test.txt");
    expect(read).toBeDefined();
    expect(read!.content).toBe("hello");
    expect(() => store.writeFile("ws1", "../escape.txt", "nope")).toThrow(
      /Invalid workspace path/,
    );
  });

  it("manages todos as thread state", () => {
    const thread = {
      id: "thread_todos",
      org_id: "o1",
      owner_user_id: "u1",
      title: "Todo thread",
      status: "active" as const,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    store.createThread(thread);
    store.createRun({
      id: "run_todo_1",
      org_id: "o1",
      actor_user_id: "u1",
      source: "api",
      thread_id: thread.id,
      workspace_id: "ws_thread_todos",
      task_msg: "first",
      scopes: ["*"],
      harness_options: null,
      status: "queued",
      started_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      current_approval_id: null,
      claim: null,
      result: null,
      error: null,
    });
    store.createRun({
      id: "run_todo_2",
      org_id: "o1",
      actor_user_id: "u1",
      source: "api",
      thread_id: thread.id,
      workspace_id: "ws_thread_todos",
      task_msg: "second",
      scopes: ["*"],
      harness_options: null,
      status: "queued",
      started_at: "2026-01-01T00:00:01Z",
      completed_at: null,
      current_approval_id: null,
      claim: null,
      result: null,
      error: null,
    });
    const todo = store.createTodo({
      id: "todo1",
      run_id: "run_todo_1",
      title: "Do stuff",
      status: "pending",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    expect(todo.id).toBe("todo1");
    expect(todo.thread_id).toBe(thread.id);
    const updated = store.updateTodo("run_todo_2", "todo1", { status: "done" });
    expect(updated.status).toBe("done");
    const todos = store.listTodos("run_todo_2");
    expect(todos).toHaveLength(1);
  });
});
