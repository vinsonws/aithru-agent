import type { ServerResponse } from "node:http";

export type SseConnection = {
  write(eventPayload: string): void;
  close(): void;
};

const HEARTBEAT_INTERVAL_MS = 15_000;

/**
 * Set up an SSE response on the given ServerResponse.
 *
 * Returns an SseConnection with `.write(data)` and `.close()`.
 * The response auto-closes on client disconnect.
 * A heartbeat comment is sent every 15 seconds to keep the connection alive.
 */
export function setupSse(res: ServerResponse): SseConnection {
  res.writeHead(200, {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache",
    "connection": "keep-alive",
  });

  // Flush headers immediately
  res.flushHeaders();

  const heartbeat = setInterval(() => {
    try {
      res.write(": heartbeat\n\n");
    } catch {
      clearInterval(heartbeat);
    }
  }, HEARTBEAT_INTERVAL_MS);

  // Clean up on client disconnect
  res.on("close", () => {
    clearInterval(heartbeat);
  });

  return {
    write(eventPayload: string) {
      try {
        res.write(eventPayload);
      } catch {
        clearInterval(heartbeat);
      }
    },
    close() {
      clearInterval(heartbeat);
      try {
        res.end();
      } catch { /* ignore */ }
    },
  };
}
