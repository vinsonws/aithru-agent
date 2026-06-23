import type { ComposerMode } from "./composerState";

export type SlashCommandResult =
  | { kind: "send"; goal: string; modeOverride?: ComposerMode }
  | { kind: "draft"; draft: string; modeOverride?: ComposerMode }
  | { kind: "local"; action: "status" | "clear" };

export interface SlashCommandContext {
  activeRunGoal?: string | null;
}

export function parseSlashCommand(
  rawInput: string,
  context: SlashCommandContext,
): SlashCommandResult {
  const input = rawInput.trim();
  if (!input.startsWith("/")) return { kind: "send", goal: input };

  const [commandToken, ...rest] = input.split(/\s+/);
  const command = commandToken.toLowerCase();
  const body = rest.join(" ").trim();

  if (command === "/plan") {
    if (body) return { kind: "send", goal: body, modeOverride: "plan" };
    return {
      kind: "draft",
      draft: "Plan the task before making changes.",
      modeOverride: "plan",
    };
  }

  if (command === "/status") {
    return { kind: "local", action: "status" };
  }

  if (command === "/retry") {
    return {
      kind: "draft",
      draft: context.activeRunGoal
        ? `Retry this task: ${context.activeRunGoal}`
        : "Retry the last task with the same intent.",
    };
  }

  if (command === "/clear") {
    return { kind: "local", action: "clear" };
  }

  return { kind: "send", goal: input };
}
