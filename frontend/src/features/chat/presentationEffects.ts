import type { PresentationEntry } from "./useRunStream";

const PREVIEWABLE_VIEWS = new Set<PresentationEntry["preferredView"]>([
  "html_preview",
  "source_text",
  "markdown",
  "json",
  "image",
  "pdf",
]);

export function presentationEffectKey(presentation: PresentationEntry): string {
  return `${presentation.id}:${presentation.lastSequence ?? presentation.sequence ?? "initial"}`;
}

export function previewTargetForPresentationEffect(presentation: PresentationEntry): string | null {
  if (presentation.status !== "ready") return null;
  if (!presentation.effects?.some((effect) => effect.kind === "open_panel" && effect.panel === "preview")) {
    return null;
  }
  if (!PREVIEWABLE_VIEWS.has(presentation.preferredView)) return null;
  if (!presentation.availableViews.includes(presentation.preferredView)) return null;
  if (
    !presentation.actions?.some(
      (action) => action.kind === "open_view" && action.view === presentation.preferredView,
    )
  ) {
    return null;
  }
  return previewFileId(presentation);
}

function previewFileId(presentation: PresentationEntry): string | null {
  if (presentation.resource.kind === "workspace_file" && presentation.resource.path) {
    return `ws-${presentation.resource.path}`;
  }
  if (presentation.resource.kind === "artifact" && presentation.resource.id) {
    return `artifact-${presentation.resource.id}`;
  }
  return null;
}
