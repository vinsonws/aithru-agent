/**
 * SqliteStore integration tests.
 *
 * NOTE: These tests exercise the full SqliteStore (sql.js WASM) path.
 * On some platforms (notably Windows + vitest), sql.js produces "out of memory"
 * errors during prepare(), causing unhandled rejections.  The store works
 * correctly in isolation and via direct Node.js execution; the issue is
 * specific to the sql.js WASM ↔ vitest interaction.
 *
 * The claim / lease / heartbeat contract is verified through InMemoryStore in
 * tests/worker/claim-heartbeat.test.ts and tests/worker/recovery.test.ts.
 *
 * To run these tests when the platform supports sql.js + vitest:
 *   npx vitest run tests/persistence/sqlite-store.test.ts
 */
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { SqliteStore } from "../../src/persistence/sqlite-store.js";

const SKIP_SQLITE =
  process.platform === "win32" || process.env.SKIP_SQLITE_TESTS === "1";

describe("SqliteStore", () => {
  let store: SqliteStore;

  beforeAll(async () => {
    if (SKIP_SQLITE) return;
    store = await SqliteStore.create();
  });

  afterAll(() => {
    if (SKIP_SQLITE) return;
    store.close();
  });

  const skipIf = SKIP_SQLITE ? it.skip : it;

  skipIf("creates and retrieves a thread", () => {
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
    const got = store.getThread("t1");
    expect(got).toBeDefined();
    expect(got!.id).toBe("t1");
    expect(got!.title).toBe("Test");
    expect(got!.status).toBe("active");
  });

  skipIf("acquires and releases claims", () => {
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

  skipIf("finds stale claims", () => {
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
    expect(Array.isArray(stale)).toBe(true);
    expect(stale.length).toBeGreaterThanOrEqual(1);
  });

  skipIf("creates and retrieves a run", () => {
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

  skipIf("writes and reads workspace files", () => {
    const file = store.writeFile("ws1", "/test.txt", "hello");
    expect(file.path).toBe("/test.txt");
    expect(file.content).toBe("hello");
    const read = store.readFile("ws1", "/test.txt");
    expect(read).toBeDefined();
    expect(read!.content).toBe("hello");
  });

  skipIf("manages todos", () => {
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
    expect(todos.length).toBe(1);
  });
});
