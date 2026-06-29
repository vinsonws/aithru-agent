import { Download, ExternalLink, FileText, Image, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PresentationEntry } from "./useRunStream";

interface PresentationItemProps {
  presentation: PresentationEntry;
  onPreviewFile?: (fileId: string) => void;
}

export function PresentationItem({ presentation, onPreviewFile }: PresentationItemProps) {
  const previewAction = presentation.actions?.find(
    (action) => action.kind === "open_view" && action.view === presentation.preferredView,
  );
  const downloadAction = presentation.actions?.find((action) => action.kind === "download");
  const previewId = previewFileId(presentation);
  const canPreview = Boolean(previewAction && previewId && onPreviewFile);
  const downloadHref = downloadAction ? downloadUrl(presentation) : null;
  const Icon = iconForPresentation(presentation);

  return (
    <div className="py-2">
      <div className="rounded-lg border bg-card p-3 text-sm shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
            <Icon className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium text-foreground">{presentation.title}</div>
            {(presentation.reason || presentation.summary) && (
              <div className="truncate text-xs text-muted-foreground">
                {presentation.reason || presentation.summary}
              </div>
            )}
          </div>
          {canPreview && (
            <button
              type="button"
              onClick={() => previewId && onPreviewFile?.(previewId)}
              className={cn(
                "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium",
                "text-primary hover:bg-primary/10",
              )}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              {actionLabel(previewAction, "Preview")}
            </button>
          )}
          {downloadHref && (
            <a
              href={downloadHref}
              className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <Download className="h-3.5 w-3.5" />
              {actionLabel(downloadAction, "Download")}
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function previewFileId(presentation: PresentationEntry): string | null {
  if (!presentation.availableViews.includes(presentation.preferredView)) return null;
  if (presentation.resource.kind === "workspace_file" && presentation.resource.path) {
    return `ws-${presentation.resource.path}`;
  }
  return null;
}

function downloadUrl(presentation: PresentationEntry): string | null {
  if (presentation.resource.kind === "workspace_file" && presentation.resource.path) {
    const workspaceId = presentation.metadata?.workspace_id;
    if (typeof workspaceId !== "string" || !workspaceId) return null;
    const encodedPath = presentation.resource.path
      .replace(/^\/+/, "")
      .split("/")
      .filter(Boolean)
      .map(encodeURIComponent)
      .join("/");
    return `/api/workspaces/${encodeURIComponent(workspaceId)}/files/${encodedPath}/download`;
  }
  return null;
}

function actionLabel(action: NonNullable<PresentationEntry["actions"]>[number] | undefined, fallback: string): string {
  return action?.label?.trim() || fallback;
}

function iconForPresentation(presentation: PresentationEntry) {
  if (presentation.resource.kind === "approval") return ShieldCheck;
  if (presentation.preferredView === "image") return Image;
  return FileText;
}
