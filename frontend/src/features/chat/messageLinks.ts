export function copyMessageContentWithWorkspaceLinks(
  message: { role: string; content: string },
  _resolveHref?: (href: string) => string,
): string {
  return message.content;
}

export function buildWorkspaceLinkResolver(): (href: string) => string {
  return (href: string) => href;
}
