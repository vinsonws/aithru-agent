export type PromptTemplateMode = "auto" | "plan" | "chat";

export interface PromptTemplate {
  id: "build" | "debug" | "summarize" | "plan" | "research";
  titleKey: string;
  fallbackTitle: string;
  descriptionKey: string;
  fallbackDescription: string;
  prompt: string;
  mode: PromptTemplateMode;
}

const TEMPLATES: PromptTemplate[] = [
  {
    id: "build",
    titleKey: "chat:templates.build.title",
    fallbackTitle: "Build",
    descriptionKey: "chat:templates.build.description",
    fallbackDescription: "Change or add code to a project",
    prompt: "Change the current project so that...",
    mode: "auto",
  },
  {
    id: "debug",
    titleKey: "chat:templates.debug.title",
    fallbackTitle: "Debug",
    descriptionKey: "chat:templates.debug.description",
    fallbackDescription: "Investigate and fix a failure",
    prompt: "Investigate this failure, identify the root cause, and make the smallest safe fix:",
    mode: "plan",
  },
  {
    id: "summarize",
    titleKey: "chat:templates.summarize.title",
    fallbackTitle: "Summarize",
    descriptionKey: "chat:templates.summarize.description",
    fallbackDescription: "Read and summarize files",
    prompt: "Read the relevant files and summarize what matters for:",
    mode: "chat",
  },
  {
    id: "plan",
    titleKey: "chat:templates.plan.title",
    fallbackTitle: "Plan",
    descriptionKey: "chat:templates.plan.description",
    fallbackDescription: "Design an implementation plan",
    prompt: "Design an implementation plan for:",
    mode: "plan",
  },
  {
    id: "research",
    titleKey: "chat:templates.research.title",
    fallbackTitle: "Research",
    descriptionKey: "chat:templates.research.description",
    fallbackDescription: "Research with evidence and sources",
    prompt: "Research this question, cite the evidence you used, and produce a concise answer:",
    mode: "auto",
  },
];

export function getPromptTemplates(): PromptTemplate[] {
  return TEMPLATES.map((t) => ({ ...t }));
}
