import { FileText, FileCode, Image, Eye } from "lucide-react";
import type { RunFileView } from "@/features/inspection/runFilesView";
import { useTranslation } from "react-i18next";

interface FileCardProps {
  file: RunFileView;
  onPreview: () => void;
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  Image: <Image className="h-4 w-4" />,
  Markdown: <FileText className="h-4 w-4" />,
  JSON: <FileCode className="h-4 w-4" />,
  TypeScript: <FileCode className="h-4 w-4" />,
  JavaScript: <FileCode className="h-4 w-4" />,
  Python: <FileCode className="h-4 w-4" />,
};

export function FileCard({ file, onPreview }: FileCardProps) {
  const { t } = useTranslation("chat");
  const icon = TYPE_ICONS[file.typeLabel] ?? <FileText className="h-4 w-4" />;

  return (
    <div className="my-2 rounded-lg border bg-card p-3 text-sm">
      <div className="flex items-center gap-3">
        <span className="shrink-0 text-muted-foreground">{icon}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{file.name}</div>
          <div className="text-[11px] text-muted-foreground">{file.typeLabel}</div>
        </div>
        {file.canPreview && (
          <button
            type="button"
            onClick={onPreview}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-primary/10"
            title={t("chat:files.preview", "Preview")}
          >
            <Eye className="h-3.5 w-3.5" />
            {t("chat:files.preview", "Preview")}
          </button>
        )}
      </div>
    </div>
  );
}
