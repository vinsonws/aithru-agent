export type RunFileKind = "output_file" | "modified_file";
export type PreferredFileView = "html_preview" | "markdown" | "json" | "image" | "pdf" | "source_text" | "download";
export type FileLifecycle = "draft" | "persisted";
export type ResolvedFileViewer = { view: PreferredFileView; reason: "user" | "safety" | "preferred_view" | "file_type" };

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
  isDraft?: boolean;
  draftContent?: string;
  draftStatus?: DraftWorkspaceFileInput["status"];
  draftRevision?: string | number;
  preferredView?: PreferredFileView;
}

export type RunFilePreviewKind = "markdown" | "json" | "code" | "text" | "image" | "pdf" | "html" | "unsupported";

export interface WorkspaceFilePresentationHint {
  path: string;
  preferredView?: PreferredFileView;
}

interface WorkspaceFileInput {
  path: string;
  size?: number;
  media_type?: string | null;
  created_at?: string | null;
}

export interface ToolInputDraftInput {
  inputStreamId: string;
  toolCallId?: string;
  toolName?: string;
  inputText: string;
  status: "streaming" | "proposed" | "completed" | "failed" | "denied";
  lastSequence?: number;
}

export interface DraftWorkspaceFileInput {
  id: string;
  path: string;
  name: string;
  content: string;
  sourceToolCallId?: string;
  sourceInputStreamId: string;
  status: ToolInputDraftInput["status"];
  lastSequence?: number;
  preferredView?: PreferredFileView;
}

export function buildRunFileViews(input: {
  snapshot?: unknown;
  workspaceId?: string | null;
  workspaceFiles?: WorkspaceFileInput[];
  draftWorkspaceFiles?: DraftWorkspaceFileInput[];
  presentationHints?: WorkspaceFilePresentationHint[];
}): RunFileView[] {
  const result: RunFileView[] = [];

  const workspaceFiles = (input.workspaceFiles ?? []).filter(Boolean);
  const realPaths = new Set(workspaceFiles.map((f) => normalizeWorkspacePath(f.path)));
  const hints = new Map(
    (input.presentationHints ?? [])
      .flatMap((hint) => {
        const preferredView = normalizePreferredFileView(hint.preferredView);
        return preferredView ? [[normalizeWorkspacePath(hint.path), preferredView]] : [];
      }),
  );
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
      preferredView: hints.get(normalizeWorkspacePath(f.path)),
    });
  }

  for (const draft of input.draftWorkspaceFiles ?? []) {
    if (realPaths.has(normalizeWorkspacePath(draft.path))) continue;
    const previewKind = previewKindForFile({ name: draft.name });
    result.push({
      id: draft.id,
      kind: outputLikePath(draft.path) ? "output_file" : "modified_file",
      name: draft.name,
      path: draft.path,
      typeLabel: inferFileTypeLabel({ name: draft.name }),
      sizeLabel: formatFileSize(new TextEncoder().encode(draft.content).length),
      canDownload: false,
      canPreview: previewKind !== "unsupported" && !["image", "pdf"].includes(previewKind),
      previewKind,
      language: languageForFile(draft.name),
      isDraft: true,
      draftContent: draft.content,
      draftStatus: draft.status,
      draftRevision: draft.lastSequence ?? draft.content.length,
      preferredView: draft.preferredView,
    });
  }

  return result;
}

export function buildDraftWorkspaceFiles(
  toolInputDrafts: ToolInputDraftInput[] = [],
): DraftWorkspaceFileInput[] {
  const files: DraftWorkspaceFileInput[] = [];
  for (const draft of toolInputDrafts) {
    if (draft.toolName !== "workspace.write_file") continue;
    if (draft.status === "failed" || draft.status === "denied") continue;
    const extracted = extractWorkspaceWriteDraft(draft.inputText);
    if (!extracted) continue;
    const pathParts = extracted.path.split("/");
    const name = pathParts[pathParts.length - 1] || extracted.path;
    const file: DraftWorkspaceFileInput = {
      id: `ws-${extracted.path}`,
      path: extracted.path,
      name,
      content: extracted.content,
      sourceToolCallId: draft.toolCallId,
      sourceInputStreamId: draft.inputStreamId,
      status: draft.status,
      lastSequence: draft.lastSequence,
    };
    if (extracted.preferredView) file.preferredView = extracted.preferredView;
    files.push(file);
  }
  return files;
}

export function normalizePreferredFileView(value: unknown): PreferredFileView | undefined {
  return typeof value === "string" && PREFERRED_FILE_VIEWS.has(value as PreferredFileView)
    ? (value as PreferredFileView)
    : undefined;
}

export function resolveFileViewer(input: {
  file: Pick<RunFileView, "previewKind" | "isDraft" | "preferredView">;
  preferredView?: PreferredFileView;
  userView?: PreferredFileView;
}): ResolvedFileViewer {
  const { file } = input;
  const preferredView = input.preferredView ?? file.preferredView;
  const isDraftHtml = file.isDraft && file.previewKind === "html";
  if (isDraftHtml) return { view: "source_text", reason: "safety" };
  if (input.userView && isPreferredViewAllowed(file.previewKind, input.userView)) {
    return { view: input.userView, reason: "user" };
  }
  if (preferredView && isPreferredViewAllowed(file.previewKind, preferredView)) {
    return { view: preferredView, reason: "preferred_view" };
  }
  if (file.previewKind === "html") return { view: file.isDraft ? "source_text" : "html_preview", reason: file.isDraft ? "safety" : "file_type" };
  if (["markdown", "json", "image", "pdf"].includes(file.previewKind)) {
    return { view: file.previewKind as PreferredFileView, reason: "file_type" };
  }
  return { view: file.previewKind === "unsupported" ? "download" : "source_text", reason: "file_type" };
}

function isPreferredViewAllowed(previewKind: RunFilePreviewKind, view: PreferredFileView): boolean {
  if (previewKind === "html") return view === "html_preview" || view === "source_text" || view === "download";
  if (previewKind === "markdown") return view === "markdown" || view === "source_text" || view === "download";
  if (previewKind === "json") return view === "json" || view === "source_text" || view === "download";
  if (previewKind === "image") return view === "image" || view === "download";
  if (previewKind === "pdf") return view === "pdf" || view === "download";
  if (previewKind === "code" || previewKind === "text") return view === "source_text" || view === "download";
  return view === "download";
}

const PREFERRED_FILE_VIEWS = new Set<PreferredFileView>([
  "html_preview",
  "markdown",
  "json",
  "image",
  "pdf",
  "source_text",
  "download",
]);

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

function normalizeWorkspacePath(path: string): string {
  return path.replace(/^\/+/, "");
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function decodeJsonEscape(char: string): string {
  if (char === "n") return "\n";
  if (char === "r") return "\r";
  if (char === "t") return "\t";
  if (char === '"') return '"';
  if (char === "\\") return "\\";
  return char;
}

function readJsonStringProperty(
  source: string,
  key: string,
  options: { allowUnclosed?: boolean } = {},
): string | undefined {
  const keyIndex = source.indexOf(`"${key}"`);
  if (keyIndex < 0) return undefined;
  const colonIndex = source.indexOf(":", keyIndex + key.length + 2);
  if (colonIndex < 0) return undefined;
  const quoteIndex = source.indexOf('"', colonIndex + 1);
  if (quoteIndex < 0) return undefined;

  let result = "";
  let escaped = false;
  for (let index = quoteIndex + 1; index < source.length; index += 1) {
    const char = source[index];
    if (escaped) {
      result += decodeJsonEscape(char);
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (char === '"') return result;
    result += char;
  }

  return options.allowUnclosed ? result : undefined;
}

function extractWorkspaceWriteDraft(inputText: string): { path: string; content: string; preferredView?: PreferredFileView } | null {
  try {
    const parsed = JSON.parse(inputText);
    if (isRecord(parsed) && typeof parsed.path === "string" && typeof parsed.content === "string") {
      return {
        path: parsed.path,
        content: parsed.content,
        preferredView: normalizePreferredFileView(parsed.preferred_view),
      };
    }
  } catch {
    const path = readJsonStringProperty(inputText, "path");
    if (!path) return null;
    return {
      path,
      content: readJsonStringProperty(inputText, "content", { allowUnclosed: true }) ?? "",
      preferredView: normalizePreferredFileView(readJsonStringProperty(inputText, "preferred_view")),
    };
  }

  return null;
}
