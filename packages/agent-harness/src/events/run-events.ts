import type { RunId, ThreadId, MessageId, TodoId } from "@aithru/agent-core";
import { AgentError } from "@aithru/agent-core";
import type { AgentEventWriter, AgentStreamEvent } from "@aithru/agent-stream";
import { ev } from "./event-input.js";

/**
 * Emit normal completion: model.completed → todo.completed → message.completed → run.completed.
 */
export async function* emitCompletion(
  writer: AgentEventWriter,
  runId: RunId,
  threadId: ThreadId | undefined,
  msgId: MessageId,
  todoId: TodoId,
): AsyncGenerator<AgentStreamEvent> {
  yield await writer.write(ev({
    runId, threadId, type: "model.completed", source: { kind: "model" },
    payload: {},
  }));
  yield await writer.write(ev({
    runId, threadId, type: "todo.completed", source: { kind: "harness" },
    payload: { todoId, title: "Process user request", status: "done", order: 1 },
  }));
  yield await writer.write(ev({
    runId, threadId, type: "message.completed", source: { kind: "harness" },
    payload: { messageId: msgId, role: "assistant" },
  }));
  yield await writer.write(ev({
    runId, threadId, type: "run.completed", source: { kind: "harness" },
    payload: { status: "completed" },
  }));
}

/**
 * Emit run failure.  If `options.emitModelFailed` is true, emits model.failed first.
 */
export async function* emitRunFailed(
  writer: AgentEventWriter,
  runId: RunId,
  threadId: ThreadId | undefined,
  err: unknown,
  options?: { emitModelFailed?: boolean },
): AsyncGenerator<AgentStreamEvent> {
  const code = err instanceof AgentError ? err.code : "MODEL_FAILED";
  const message = err instanceof Error ? err.message.replace(/^\[[^\]]+\]\s*/, "") : String(err);

  if (options?.emitModelFailed) {
    yield await writer.write(ev({
      runId, threadId, type: "model.failed", source: { kind: "model" },
      payload: { error: { code, message, retryable: err instanceof AgentError ? err.retryable : false } },
    }));
  }

  yield await writer.write(ev({
    runId, threadId, type: "run.failed", source: { kind: "harness" },
    payload: {
      status: "failed",
      error: { code, message, retryable: err instanceof AgentError ? err.retryable : false },
    },
  }));
}
