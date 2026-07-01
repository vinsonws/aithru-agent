import { EventEmitter } from "node:events";
import { describe, it, expect, vi, afterEach } from "vitest";
import type { FastifyReply, FastifyRequest } from "fastify";
import type { AgentRun } from "@aithru-agent/contracts";
import { InMemoryStore } from "@aithru-agent/persistence";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import type { AgentRuntime } from "../../apps/api/src/runtime.js";
import { writeRunStream } from "../../apps/api/src/routes/run-stream.js";

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function createRun(id: string, status: AgentRun["status"]): AgentRun {
  return {
    id,
    org_id: "org_1",
    actor_user_id: "user_1",
    source: "chat",
    thread_id: null,
    workspace_id: `ws_${id}`,
    task_msg: "stream test",
    scopes: ["*"],
    harness_options: null,
    status,
    current_approval_id: null,
    started_at: now(),
    completed_at: status === "completed" ? now() : null,
    claim: null,
    result: null,
    error: null,
  };
}

class MockRaw extends EventEmitter {
  destroyed = false;
  writableEnded = false;
  statusCode: number | null = null;
  headers: Record<string, string> = {};
  chunks: string[] = [];

  writeHead(statusCode: number, headers: Record<string, string>) {
    this.statusCode = statusCode;
    this.headers = headers;
    return this;
  }

  write(chunk: string | Buffer) {
    this.chunks.push(String(chunk));
    return true;
  }

  end(chunk?: string | Buffer) {
    if (chunk != null) this.chunks.push(String(chunk));
    this.writableEnded = true;
    this.emit("finish");
    return this;
  }

  text(): string {
    return this.chunks.join("");
  }
}

function createReply(raw: MockRaw): FastifyReply {
  return { raw } as unknown as FastifyReply;
}

function createRuntime(runStatus: AgentRun["status"] = "running"): {
  runtime: AgentRuntime;
  run: AgentRun;
  raw: MockRaw;
} {
  const store = new InMemoryStore();
  const eventWriter = new AgentEventWriter(store);
  const run = createRun("run_stream_test", runStatus);
  store.createRun(run);
  return {
    runtime: { store, eventWriter } as unknown as AgentRuntime,
    run,
    raw: new MockRaw(),
  };
}

describe("writeRunStream", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("pushes follow-mode events without waiting for a polling interval", async () => {
    vi.useFakeTimers();
    const { runtime, run, raw } = createRuntime("running");
    runtime.eventWriter.write(run.id, null, EVENT_TYPES.RUN_STARTED, { status: "running" });

    const stream = writeRunStream({
      request: {} as FastifyRequest,
      reply: createReply(raw),
      runtime,
      runId: run.id,
      minSequence: 1,
      follow: true,
    });

    await Promise.resolve();
    runtime.eventWriter.write(run.id, null, EVENT_TYPES.MESSAGE_DELTA, {
      message_id: "msg_1",
      delta: "live token",
    });
    await Promise.resolve();

    expect(raw.text()).toContain("event: message.delta");
    expect(raw.text()).toContain("live token");

    runtime.store.updateRun(run.id, { status: "completed", completed_at: now() });
    runtime.eventWriter.write(run.id, null, EVENT_TYPES.RUN_COMPLETED, { status: "completed" });
    await stream;

    expect(raw.writableEnded).toBe(true);
  });

  it("replays stored events after after_sequence and ends on terminal runs", async () => {
    const { runtime, run, raw } = createRuntime("completed");
    runtime.eventWriter.write(run.id, null, EVENT_TYPES.RUN_STARTED, { status: "running" });
    runtime.eventWriter.write(run.id, null, EVENT_TYPES.MESSAGE_DELTA, {
      message_id: "msg_2",
      delta: "replayed token",
    });
    runtime.eventWriter.write(run.id, null, EVENT_TYPES.RUN_COMPLETED, { status: "completed" });

    await writeRunStream({
      request: {} as FastifyRequest,
      reply: createReply(raw),
      runtime,
      runId: run.id,
      minSequence: 1,
      follow: true,
    });

    expect(raw.text()).not.toContain('"sequence":1');
    expect(raw.text()).toContain('"sequence":2');
    expect(raw.text()).toContain("replayed token");
    expect(raw.text()).toContain('"sequence":3');
    expect(raw.writableEnded).toBe(true);
  });
});
