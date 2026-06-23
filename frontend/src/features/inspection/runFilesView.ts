export type RunFileKind = "artifact" | "workspace_file";

export interface RunFileView {
  id: string;
  kind: RunFileKind;
  name: string;
  path?: string;
  typeLabel: string;
  sizeLabel?: string;
  createdAt?: string | null;
  href?: string;
  canDownload: boolean;
  canPreview: boolean;
}

interface ArtifactInput {
  id: string;
  name: string;
  type?: string;
  media_type?: string | null;
  created_at?: string;
  finalized?: unknown;
}

interface WorkspaceFileInput {
  path: string;
  size?: number;
  media_type?: string | null;
}

export function buildRunFileViews(input: {
  snapshot?: unknown;
  workspaceFiles?: WorkspaceFileInput[];
  artifacts?: ArtifactInput[];
}): RunFileView[] {
  const result: RunFileView[] = [];

  const artifacts = (input.artifacts ?? []).filter(Boolean);
  const finalized = artifacts.filter((a) => a.finalized);
  const remaining = artifacts.filter((a) => !a.finalized);

  for (const a of [...finalized, ...remaining]) {
    const name = a.name || "unnamed";
    result.push({
      id: `artifact-${a.id}`,
      kind: "artifact",
      name,
      path: a.name,
      typeLabel: inferFileTypeLabel({ name, mediaType: a.media_type, artifactType: a.type }),
      createdAt: a.created_at,
      href: `/api/artifacts/${a.id}/content`,
      canDownload: true,
      canPreview: true,
    });
  }

  const workspaceFiles = (input.workspaceFiles ?? []).filter(Boolean);
  for (const f of workspaceFiles) {
    const pathParts = f.path.split("/");
    const name = pathParts[pathParts.length - 1] || f.path;
    result.push({
      id: `ws-${f.path}`,
      kind: "workspace_file",
      name,
      path: f.path,
      typeLabel: inferFileTypeLabel({ name, mediaType: f.media_type }),
      sizeLabel: formatFileSize(f.size),
      canDownload: false,
      canPreview: true,
    });
  }

  return result;
}

const EXTENSION_TYPE_MAP: Record<string, string> = {
  md: "Markdown",
  markdown: "Markdown",
  json: "JSON",
  ts: "TypeScript",
  tsx: "TypeScript",
  js: "JavaScript",
  jsx: "JavaScript",
  py: "Python",
  txt: "Text",
  csv: "CSV",
  yaml: "YAML",
  yml: "YAML",
  toml: "TOML",
  html: "HTML",
  css: "CSS",
  svg: "Image",
  png: "Image",
  jpg: "Image",
  jpeg: "Image",
  gif: "Image",
  webp: "Image",
  ico: "Image",
};

const MEDIA_TYPE_MAP: Record<string, string> = {
  "image/": "Image",
  "text/": "Text",
  "application/json": "JSON",
};

export function inferFileTypeLabel(input: {
  name?: string | null;
  path?: string | null;
  mediaType?: string | null;
  artifactType?: string | null;
}): string {
  const mediaType = input.mediaType;
  if (mediaType) {
    for (const [prefix, label] of Object.entries(MEDIA_TYPE_MAP)) {
      if (mediaType.startsWith(prefix)) return label;
    }
  }

  const name = input.name || input.path || "";
  const dotIndex = name.lastIndexOf(".");
  if (dotIndex >= 0) {
    const ext = name.slice(dotIndex + 1).toLowerCase();
    if (EXTENSION_TYPE_MAP[ext]) return EXTENSION_TYPE_MAP[ext];
  }

  return "File";
}

export function formatFileSize(bytes?: number | null): string | undefined {
  if (bytes == null) return undefined;
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, unitIndex);
  return `${Math.round(value)} ${units[unitIndex]}`;
}
