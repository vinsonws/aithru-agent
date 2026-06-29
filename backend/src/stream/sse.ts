import type { AgentStreamEvent } from "../contracts/types.js";

export function formatSseEvent(event: AgentStreamEvent): string {
  const data = JSON.stringify(event);
  return `id: ${event.id}\nevent: ${event.type}\ndata: ${data}\n\n`;
}

export function formatSseComment(comment: string): string {
  const safe = comment.replace(/\r/g, " ").replace(/\n/g, " ");
  return `: ${safe}\n\n`;
}
