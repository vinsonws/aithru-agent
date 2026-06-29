import type { PresentationEntry, RunStreamState } from "./useRunStream";

const AITHRU_ARTIFACT_URL_RE = /^https:\/\/aithru\.ai\/artifact\/([^/?#]+)\/([^/?#]+)([?#].*)?$/i;
const MARKDOWN_LINK_DESTINATION_RE = /(\]\()([^)]+)(\))/g;

export function artifactContentHref(artifactId: string): string {
  return `/api/artifacts/${encodeURIComponent(artifactId)}/content`;
}

export function artifactIdsFromRunStates(states: RunStreamState[]): Set<string> {
  const ids = new Set<string>();
  for (const state of states) {
    for (const presentation of state.presentations ?? []) {
      const artifactId = artifactIdFromPresentation(presentation);
      if (artifactId) ids.add(artifactId);
    }
  }
  return ids;
}

export function resolveKnownArtifactHref(
  href: string,
  artifactIds: ReadonlySet<string>,
): string {
  const match = AITHRU_ARTIFACT_URL_RE.exec(href.trim());
  if (!match) return href;

  const artifactId = decodeUrlComponent(match[2]);
  if (artifactId === null) return href;
  if (!artifactIds.has(artifactId)) return href;

  return artifactContentHref(artifactId);
}

export function buildArtifactLinkResolver(states: RunStreamState[]): (href: string) => string {
  const artifactIds = artifactIdsFromRunStates(states);
  return (href: string) => resolveKnownArtifactHref(href, artifactIds);
}

export function rewriteKnownArtifactMarkdownLinks(
  markdown: string,
  resolveHref: (href: string) => string,
): string {
  return markdown.replace(MARKDOWN_LINK_DESTINATION_RE, (full, open, href, close) => {
    const resolved = resolveHref(href.trim());
    return resolved === href.trim() ? full : `${open}${resolved}${close}`;
  });
}

export function copyMessageContentWithArtifactLinks(
  message: { role: string; content: string },
  resolveHref?: (href: string) => string,
): string {
  if (message.role !== "assistant" || !resolveHref) return message.content;
  return rewriteKnownArtifactMarkdownLinks(message.content, resolveHref);
}

function artifactIdFromPresentation(presentation: PresentationEntry): string | null {
  if (presentation.resource.kind !== "artifact") return null;
  const id = presentation.resource.id?.trim();
  return id || null;
}

function decodeUrlComponent(value: string): string | null {
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}
