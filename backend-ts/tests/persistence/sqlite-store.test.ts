import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { SqliteStore } from "../../src/persistence/sqlite-store.js";

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

  it("writes and reads workspace files", () => {
    const file = store.writeFile("ws1", "/test.txt", "hello");
    expect(file.path).toBe("/test.txt");
    expect(file.content).toBe("hello");
    const read = store.readFile("ws1", "/test.txt");
    expect(read).toBeDefined();
    expect(read!.content).toBe("hello");
  });

  it("manages todos", () => {
    const todo = store.createTodo({
      id: "todo1",
      run_id: "r3",
      title: "Do stuff",
      status: "pending",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    expect(todo.id).toBe("todo1");
    const updated = store.updateTodo("r3", "todo1", { status: "done" });
    expect(updated.status).toBe("done");
    const todos = store.listTodos("r3");
    expect(todos).toHaveLength(1);
  });
});
