import type { ComposerMode } from "./composerState";

export type SlashCommandResult =
  | { kind: "send"; taskMsg: string; modeOverride?: ComposerMode }
  | { kind: "draft"; draft: string; modeOverride?: ComposerMode }
  | { kind: "local"; action: "status" | "clear" };

export interface SlashCommandContext {
  activeRunTaskMsg?: string | null;
}

export function parseSlashCommand(
  rawInput: string,
  context: SlashCommandContext,
): SlashCommandResult {
  const input = rawInput.trim();
  if (!input.startsWith("/")) return { kind: "send", taskMsg: input };

  const [commandToken, ...rest] = input.split(/\s+/);
  const command = commandToken.toLowerCase();
  const body = rest.join(" ").trim();

  if (command === "/plan") {
    if (body) return { kind: "send", taskMsg: body, modeOverride: "pro" };
    return {
      kind: "draft",
      draft: "Plan the task before making changes.",
      modeOverride: "pro",
    };
  }

  if (command === "/status") {
    return { kind: "local", action: "status" };
  }

  if (command === "/retry") {
    return {
      kind: "draft",
      draft: context.activeRunTaskMsg
        ? `Retry this task: ${context.activeRunTaskMsg}`
        : "Retry the last task with the same intent.",
    };
  }

  if (command === "/clear") {
    return { kind: "local", action: "clear" };
  }

  return { kind: "send", taskMsg: input };
}
