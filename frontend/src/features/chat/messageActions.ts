export type MessageActionKind =
  | "copy"
  | "editAndRerun"
  | "continue"
  | "viewTrace";

export interface MessageActionView {
  kind: MessageActionKind;
  labelKey: string;
  fallback: string;
  disabled?: boolean;
}

interface ChatMessageLike {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  streaming?: boolean;
}

export function buildMessageActions(message: ChatMessageLike): MessageActionView[] {
  const actions: MessageActionView[] = [];

  if (message.content && message.content.length > 0) {
    actions.push({ kind: "copy", labelKey: "chat:messageActions.copy", fallback: "Copy" });
  }

  if (message.role === "user" && !message.streaming) {
    actions.push({
      kind: "editAndRerun",
      labelKey: "chat:messageActions.editAndRerun",
      fallback: "Edit and rerun",
    });
  }

  if (message.role === "assistant" && !message.streaming && message.content) {
    actions.push({
      kind: "continue",
      labelKey: "chat:messageActions.continue",
      fallback: "Continue",
    });
    actions.push({
      kind: "viewTrace",
      labelKey: "chat:messageActions.viewTrace",
      fallback: "View trace",
    });
  }

  return actions;
}

export function buildEditAndRerunPrompt(message: ChatMessageLike): string {
  return message.content;
}

export function buildContinuePrompt(message: ChatMessageLike): string {
  const excerpt = message.content.slice(0, 120).trim();
  return `Continue from where you left off:\n\n${excerpt}...`;
}

export async function copyMessageContent(message: ChatMessageLike): Promise<boolean> {
  if (!navigator?.clipboard?.writeText) return false;
  try {
    await navigator.clipboard.writeText(message.content);
    return true;
  } catch {
    return false;
  }
}
