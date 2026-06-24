export type MessageActionKind =
  | "copy"
  | "editAndRerun"
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

export async function copyMessageContent(message: ChatMessageLike): Promise<boolean> {
  if (!navigator?.clipboard?.writeText) return false;
  try {
    await navigator.clipboard.writeText(message.content);
    return true;
  } catch {
    return false;
  }
}
