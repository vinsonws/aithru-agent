import { Download, ExternalLink, FileText, Image, Package, Search, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { DisplayCardEntry } from "./useRunStream";

interface DisplayCardProps {
  card: DisplayCardEntry;
  onPreviewFile?: (fileId: string) => void;
}

const CARD_ICON = {
  file: FileText,
  artifact: Package,
  approval: ShieldCheck,
  search_result: Search,
  generic: FileText,
  todo: FileText,
  memory: FileText,
} as const;

export function DisplayCard({ card, onPreviewFile }: DisplayCardProps) {
  const { t } = useTranslation("chat");
  const Icon = CARD_ICON[card.type] ?? CARD_ICON.generic;
  const previewAction = cardAction(card, "preview");
  const downloadAction = cardAction(card, "download");
  const openAction = cardAction(card, "open");
  const previewId = previewFileId(card);
  const canPreview = Boolean(previewAction && previewId && onPreviewFile);
  const downloadHref = downloadAction ? downloadUrl(card, downloadAction) : null;
  const openHref = openAction ? openUrl(card, openAction) : null;

  return (
    <div className="py-2">
      <div className="rounded-lg border bg-card p-3 text-sm shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
            {card.type === "file" && isImageLike(card) ? (
              <Image className="h-4 w-4" />
            ) : (
              <Icon className="h-4 w-4" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium text-foreground">{card.title}</div>
            {card.summary && (
              <div className="truncate text-xs text-muted-foreground">{card.summary}</div>
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
              {actionLabel(previewAction, t("cards.preview", "Preview"))}
            </button>
          )}
          {downloadHref && (
            <a
              href={downloadHref}
              className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <Download className="h-3.5 w-3.5" />
              {actionLabel(downloadAction, t("cards.download", "Download"))}
            </a>
          )}
          {openHref && (
            <a
              href={openHref}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              {actionLabel(openAction, t("cards.open", "Open"))}
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

type DisplayCardAction = NonNullable<DisplayCardEntry["actions"]>[number];

function cardAction(
  card: DisplayCardEntry,
  kind: DisplayCardAction["kind"],
): DisplayCardAction | null {
  return card.actions?.find((action) => action.kind === kind && !action.disabled) ?? null;
}

function actionLabel(action: DisplayCardAction | null, fallback: string): string {
  const label = action?.label?.trim();
  return label || fallback;
}

function previewFileId(card: DisplayCardEntry): string | null {
  if (card.resource?.kind === "workspace_file" && card.resource.path) {
    return `ws-${card.resource.path}`;
  }
  if (card.resource?.kind === "artifact" && card.resource.id) {
    return `artifact-${card.resource.id}`;
  }
  return null;
}

function downloadUrl(card: DisplayCardEntry, action: DisplayCardAction): string | null {
  if (action.target) return action.target;
  if (card.resource?.kind === "artifact" && card.resource.id) {
    return `/api/artifacts/${encodeURIComponent(card.resource.id)}/download`;
  }
  return null;
}

function openUrl(card: DisplayCardEntry, action: DisplayCardAction): string | null {
  if (action.target) return action.target;
  if (card.resource?.kind === "external_url" && card.resource.url) return card.resource.url;
  return null;
}

function isImageLike(card: DisplayCardEntry): boolean {
  const title = card.title.toLowerCase();
  return [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"].some((suffix) =>
    title.endsWith(suffix),
  );
}
