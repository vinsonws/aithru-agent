export type RunFileKind = "output_file" | "modified_file";

export interface RunFileView {
  id: string;
  kind: RunFileKind;
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

interface WorkspaceFileInput {
  path: string;
  size?: number;
  media_type?: string | null;
  created_at?: string | null;
}

export function buildRunFileViews(input: {
  snapshot?: unknown;
  workspaceId?: string | null;
  workspaceFiles?: WorkspaceFileInput[];
}): RunFileView[] {
  const result: RunFileView[] = [];

  const workspaceFiles = (input.workspaceFiles ?? []).filter(Boolean);
  for (const f of workspaceFiles) {
    const pathParts = f.path.split("/");
    const name = pathParts[pathParts.length - 1] || f.path;
    const previewKind = previewKindForFile({ name, mediaType: f.media_type });
    result.push({
      id: `ws-${f.path}`,
      kind: outputLikePath(f.path) ? "output_file" : "modified_file",
      name,
      path: f.path,
      typeLabel: inferFileTypeLabel({ name, mediaType: f.media_type }),
      sizeLabel: formatFileSize(f.size),
      createdAt: f.created_at,
      href: input.workspaceId ? workspaceFileUrl(input.workspaceId, f.path, "/download") : undefined,
      previewHref: input.workspaceId ? workspaceFileUrl(input.workspaceId, f.path, "/content") : undefined,
      canDownload: Boolean(input.workspaceId),
      canPreview: previewKind !== "unsupported",
      previewKind,
      language: languageForFile(name),
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

export function previewKindForFile(input: {
  name?: string | null;
  mediaType?: string | null;
}): RunFilePreviewKind {
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

function outputLikePath(path: string): boolean {
  return /^\/?(outputs|reports|exports)\//.test(path);
}

function workspaceFileUrl(workspaceId: string, path: string, suffix = ""): string {
  const encodedPath = path
    .replace(/^\/+/, "")
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/files/${encodedPath}${suffix}`;
}

export function formatFileSize(bytes?: number | null): string | undefined {
  if (bytes == null) return undefined;
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, unitIndex);
  return `${Math.round(value)} ${units[unitIndex]}`;
}
