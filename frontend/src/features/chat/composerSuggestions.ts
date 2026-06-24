import type { ComposerSlashSuggestion } from "./ReferenceComposerSurface";

export const SLASH_SUGGESTIONS: ComposerSlashSuggestion[] = [
  {
    command: "/plan",
    labelKey: "chat:slash.plan.label",
    fallbackLabel: "Plan",
    descriptionKey: "chat:slash.plan.description",
    fallbackDescription: "Plan before taking action",
  },
  {
    command: "/status",
    labelKey: "chat:slash.status.label",
    fallbackLabel: "Status",
    descriptionKey: "chat:slash.status.description",
    fallbackDescription: "Show the current run status",
  },
  {
    command: "/retry",
    labelKey: "chat:slash.retry.label",
    fallbackLabel: "Retry",
    descriptionKey: "chat:slash.retry.description",
    fallbackDescription: "Retry the last task",
  },
  {
    command: "/clear",
    labelKey: "chat:slash.clear.label",
    fallbackLabel: "Clear",
    descriptionKey: "chat:slash.clear.description",
    fallbackDescription: "Clear the composer",
  },
];
