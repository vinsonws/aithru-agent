import type { FastifyReply, FastifyRequest } from "fastify";
import { TERMINAL_RUN_STATUSES } from "@aithru-agent/contracts";
import {
  EVENT_TYPES,
  formatSseComment,
  formatSseEvent,
} from "@aithru-agent/stream";
import type { AgentRuntime } from "../runtime.js";

const STREAM_POLL_INTERVAL_MS = 100;
const STREAM_KEEPALIVE_MS = 15_000;
const TERMINAL_EVENT_TYPES = new Set<string>([
  EVENT_TYPES.RUN_COMPLETED,
  EVENT_TYPES.RUN_FAILED,
  EVENT_TYPES.RUN_CANCELLED,
]);

export function shouldFollowRunStream(query: unknown): boolean {
  const raw = (query as Record<string, unknown> | null | undefined)?.follow;
  return raw === true || raw === "true" || raw === "1";
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
  reply: FastifyReply,
  runId: string,
  cursor: number,
): { cursor: number; sawTerminalEvent: boolean } {
  let nextCursor = cursor;
  let sawTerminalEvent = false;
  const events = runtime.store
    .listEvents(runId)
    .filter((event) => event.sequence > cursor);
  for (const event of events) {
    reply.raw.write(formatSseEvent(event));
    nextCursor = Math.max(nextCursor, event.sequence);
    sawTerminalEvent ||= TERMINAL_EVENT_TYPES.has(event.type);
  }
  return { cursor: nextCursor, sawTerminalEvent };
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
  reply.raw.on("close", () => {
    clientClosed = true;
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
    const result = writeEventsSince(runtime, reply, runId, cursor);
    cursor = result.cursor;
    sawTerminalEvent ||= result.sawTerminalEvent;
  };

  flush();
  reply.raw.write(formatSseComment("stream ready"));

  if (follow && !sawTerminalEvent && !isTerminalRun(runtime, runId)) {
    let lastKeepalive = Date.now();
    while (
      !clientClosed &&
      !isReplyClosed(reply) &&
      !sawTerminalEvent &&
      !isTerminalRun(runtime, runId)
    ) {
      await wait(STREAM_POLL_INTERVAL_MS);
      if (clientClosed || isReplyClosed(reply)) break;
      flush();
      const now = Date.now();
      if (!sawTerminalEvent && now - lastKeepalive >= STREAM_KEEPALIVE_MS) {
        reply.raw.write(formatSseComment("keepalive"));
        lastKeepalive = now;
      }
    }
    if (!clientClosed && !isReplyClosed(reply)) flush();
  }

  if (!clientClosed && !isReplyClosed(reply)) {
    reply.raw.end();
  }
}
