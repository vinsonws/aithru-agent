import type { FastifyReply, FastifyRequest } from "fastify";
import { TERMINAL_RUN_STATUSES } from "@aithru-agent/contracts";
import {
  EVENT_TYPES,
  formatSseComment,
  formatSseEvent,
} from "@aithru-agent/stream";
import type { AgentRuntime } from "../runtime.js";

const STREAM_KEEPALIVE_MS = 15_000;
const STREAM_BUFFER_LIMIT = 128;
const TERMINAL_EVENT_TYPES = new Set<string>([
  EVENT_TYPES.RUN_COMPLETED,
  EVENT_TYPES.RUN_FAILED,
  EVENT_TYPES.RUN_CANCELLED,
]);

export function shouldFollowRunStream(query: unknown): boolean {
  const raw = (query as Record<string, unknown> | null | undefined)?.follow;
  return raw === true || raw === "true" || raw === "1";
}

function isReplyClosed(reply: FastifyReply): boolean {
  return reply.raw.destroyed || reply.raw.writableEnded;
}

function isTerminalRun(runtime: AgentRuntime, runId: string): boolean {
  const run = runtime.store.getRun(runId);
  return !run || TERMINAL_RUN_STATUSES.has(run.status as any);
}

function writeEventsSince(
  runtime: AgentRuntime,
  writeChunk: (chunk: string) => void,
  runId: string,
  cursor: number,
): { cursor: number; sawTerminalEvent: boolean } {
  let nextCursor = cursor;
  let sawTerminalEvent = false;
  const events = runtime.store
    .listEvents(runId)
    .filter((event) => event.sequence > cursor);
  for (const event of events) {
    writeChunk(formatSseEvent(event));
    nextCursor = Math.max(nextCursor, event.sequence);
    sawTerminalEvent ||= TERMINAL_EVENT_TYPES.has(event.type);
  }
  return { cursor: nextCursor, sawTerminalEvent };
}

function createBufferedSseWriter(reply: FastifyReply) {
  let draining = false;
  let closed = false;
  let droppedCount = 0;
  const pending: string[] = [];
  const idleWaiters = new Set<() => void>();

  const resolveIdleWaiters = () => {
    if (draining || pending.length > 0) return;
    for (const resolve of idleWaiters) resolve();
    idleWaiters.clear();
  };

  const scheduleDrain = () => {
    if (draining) return;
    draining = true;
    reply.raw.once("drain", flush);
  };

  const flush = () => {
    if (closed) {
      pending.length = 0;
      resolveIdleWaiters();
      return;
    }
    draining = false;
    if (droppedCount > 0) {
      const ok = reply.raw.write(formatSseComment(`warning: dropped ${droppedCount} stream events`));
      droppedCount = 0;
      if (!ok) {
        scheduleDrain();
        return;
      }
    }
    while (pending.length > 0) {
      const ok = reply.raw.write(pending.shift()!);
      if (!ok) {
        scheduleDrain();
        return;
      }
    }
    resolveIdleWaiters();
  };

  const enqueue = (chunk: string) => {
    if (closed) return;
    if (!draining && pending.length === 0) {
      const ok = reply.raw.write(chunk);
      if (!ok) scheduleDrain();
      else resolveIdleWaiters();
      return;
    }
    if (pending.length >= STREAM_BUFFER_LIMIT) {
      pending.shift();
      droppedCount += 1;
    }
    pending.push(chunk);
  };

  return {
    enqueue,
    close() {
      closed = true;
      resolveIdleWaiters();
    },
    waitForIdle(): Promise<void> {
      if (!draining && pending.length === 0) return Promise.resolve();
      return new Promise((resolve) => {
        idleWaiters.add(resolve);
      });
    },
  };
}

export async function writeRunStream(args: {
  request: FastifyRequest;
  reply: FastifyReply;
  runtime: AgentRuntime;
  runId: string;
  minSequence: number;
  follow: boolean;
}): Promise<void> {
  const { reply, runtime, runId, minSequence, follow } = args;
  let clientClosed = false;
  const sse = createBufferedSseWriter(reply);
  reply.raw.on("close", () => {
    clientClosed = true;
    sse.close();
  });

  reply.raw.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  });

  let cursor = minSequence;
  let sawTerminalEvent = false;
  const flush = () => {
    const result = writeEventsSince(runtime, (chunk) => sse.enqueue(chunk), runId, cursor);
    cursor = result.cursor;
    sawTerminalEvent ||= result.sawTerminalEvent;
  };

  flush();
  sse.enqueue(formatSseComment("stream ready"));

  if (follow && !sawTerminalEvent && !isTerminalRun(runtime, runId)) {
    await new Promise<void>((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearInterval(keepalive);
        unsubscribe();
        resolve();
      };
      const finishAfterDrain = () => {
        void sse.waitForIdle().then(finish);
      };
      const unsubscribe = runtime.eventWriter.subscribe(runId, (event) => {
        if (clientClosed || isReplyClosed(reply)) {
          finish();
          return;
        }
        if (event.sequence <= cursor) return;
        cursor = event.sequence;
        sawTerminalEvent ||= TERMINAL_EVENT_TYPES.has(event.type);
        sse.enqueue(formatSseEvent(event));
        if (sawTerminalEvent || isTerminalRun(runtime, runId)) finishAfterDrain();
      });
      const keepalive = setInterval(() => {
        if (clientClosed || isReplyClosed(reply)) {
          finish();
          return;
        }
        if (sawTerminalEvent || isTerminalRun(runtime, runId)) {
          finishAfterDrain();
          return;
        }
        sse.enqueue(formatSseComment("keepalive"));
      }, STREAM_KEEPALIVE_MS);
    });
  }

  if (!clientClosed && !isReplyClosed(reply)) {
    await sse.waitForIdle();
    reply.raw.end();
  }
}
