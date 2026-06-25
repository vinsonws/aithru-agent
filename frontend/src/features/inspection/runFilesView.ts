export type RunFileKind = "artifact" | "modified_file";

export interface RunFileView {
  id: string;
  kind: RunFileKind;
  artifactId?: string;
  name: string;
  path?: string;
  typeLabel: string;
  sizeLabel?: string;
  createdAt?: string | null;
  href?: string;
  previewHref?: string;
  canDownload: boolean;
  canPreview: boolean;
  previewKind: RunFilePreviewKind;
  language?: string;
}

export type RunFilePreviewKind = "markdown" | "json" | "code" | "text" | "image" | "pdf" | "html" | "unsupported";

interface ArtifactInput {
  id: string;
  name: string;
  type?: string;
  media_type?: string | null;
  created_at?: string;
  finalized_at?: string | null;
  finalized?: unknown;
  uri?: string | null;
  metadata?: Record<string, unknown> | null;
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
  const finalized = artifacts.filter((a) => a.finalized || a.finalized_at);
  const remaining = artifacts.filter((a) => !a.finalized && !a.finalized_at);
  const artifactSourcePaths = new Set<string>();

  for (const a of [...finalized, ...remaining]) {
    const name = a.name || "unnamed";
    const sourcePath = artifactSourcePath(a);
    if (sourcePath) artifactSourcePaths.add(sourcePath);
    result.push({
      id: `artifact-${a.id}`,
      kind: "artifact",
      artifactId: a.id,
      name,
      path: sourcePath ?? a.name,
      typeLabel: inferFileTypeLabel({ name, mediaType: a.media_type, artifactType: a.type }),
      createdAt: a.created_at,
      href: `/api/artifacts/${a.id}/download`,
      previewHref: `/api/artifacts/${a.id}/content`,
      canDownload: true,
      canPreview: previewKindForFile({ name, mediaType: a.media_type, artifactType: a.type }) !== "unsupported",
      previewKind: previewKindForFile({ name, mediaType: a.media_type, artifactType: a.type }),
      language: languageForFile(name),
    });
  }

  const workspaceFiles = (input.workspaceFiles ?? []).filter(Boolean);
  for (const f of workspaceFiles.filter((file) => !artifactSourcePaths.has(file.path))) {
    const pathParts = f.path.split("/");
    const name = pathParts[pathParts.length - 1] || f.path;
    result.push({
      id: `ws-${f.path}`,
      kind: "modified_file",
      name,
      path: f.path,
      typeLabel: inferFileTypeLabel({ name, mediaType: f.media_type }),
      sizeLabel: formatFileSize(f.size),
      canDownload: false,
      canPreview: previewKindForFile({ name, mediaType: f.media_type }) !== "unsupported",
      previewKind: previewKindForFile({ name, mediaType: f.media_type }),
      language: languageForFile(name),
    });
  }

  return result;
}

function artifactSourcePath(artifact: ArtifactInput): string | undefined {
  const metadata = artifact.metadata ?? {};
  const sourcePath = metadata.source_path ?? metadata.workspace_path ?? metadata.path;
  if (typeof sourcePath === "string" && sourcePath.trim()) return sourcePath;
  if (artifact.uri?.startsWith("workspace://")) {
    return artifact.uri.slice("workspace://".length).replace(/^\/+/, "");
  }
  return undefined;
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
  if (input.artifactType === "markdown" || input.artifactType === "report") return "Markdown";
  if (input.artifactType === "json") return "JSON";
  if (input.artifactType === "text") return "Text";

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

export function previewKindForFile(input: {
  name?: string | null;
  mediaType?: string | null;
  artifactType?: string | null;
}): RunFilePreviewKind {
  if (input.artifactType === "markdown" || input.artifactType === "report") return "markdown";
  if (input.artifactType === "json") return "json";
  if (input.artifactType === "text") return "text";

  const mediaType = input.mediaType?.toLowerCase() ?? "";
  if (mediaType.startsWith("image/")) return "image";
  if (mediaType === "application/pdf") return "pdf";
  if (mediaType === "application/json") return "json";
  if (mediaType.startsWith("text/")) {
    if (mediaType.includes("html")) return "html";
    if (mediaType.includes("markdown")) return "markdown";
    if (mediaType.includes("css") || mediaType.includes("javascript")) return "code";
    return "text";
  }

  const ext = extensionForName(input.name);
  if (!ext) return "unsupported";
  if (["md", "markdown"].includes(ext)) return "markdown";
  if (ext === "json") return "json";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "ico"].includes(ext)) return "image";
  if (ext === "pdf") return "pdf";
  if (["txt", "log", "csv"].includes(ext)) return "text";
  if (["py", "ts", "tsx", "js", "jsx", "css", "yaml", "yml", "toml", "sh", "sql"].includes(ext)) return "code";
  if (ext === "html") return "html";
  return "unsupported";
}

export function languageForFile(name?: string | null): string | undefined {
  const ext = extensionForName(name);
  if (!ext) return undefined;
  const map: Record<string, string> = {
    js: "javascript",
    jsx: "javascript",
    ts: "typescript",
    tsx: "typescript",
    py: "python",
    md: "markdown",
    markdown: "markdown",
    json: "json",
    html: "html",
    css: "css",
    yaml: "yaml",
    yml: "yaml",
    toml: "toml",
    sh: "bash",
    sql: "sql",
    csv: "csv",
  };
  return map[ext];
}

function extensionForName(name?: string | null): string | undefined {
  const value = name ?? "";
  const dotIndex = value.lastIndexOf(".");
  if (dotIndex < 0) return undefined;
  return value.slice(dotIndex + 1).toLowerCase();
}

export function formatFileSize(bytes?: number | null): string | undefined {
  if (bytes == null) return undefined;
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, unitIndex);
  return `${Math.round(value)} ${units[unitIndex]}`;
}
