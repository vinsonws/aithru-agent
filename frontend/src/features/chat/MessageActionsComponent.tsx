import { useState, useCallback } from "react";
import { Copy, Pencil, GitBranch } from "lucide-react";
import type { MessageActionView } from "./messageActions";
import { useTranslation } from "react-i18next";

const ACTION_ICONS: Record<string, React.ReactNode> = {
  copy: <Copy className="h-3 w-3" />,
  editAndRerun: <Pencil className="h-3 w-3" />,
  viewTrace: <GitBranch className="h-3 w-3" />,
};

export function MessageActions({
  actions,
  messageId,
  onAction,
}: {
  actions: MessageActionView[];
  messageId: string;
  onAction: (kind: string, messageId: string) => void;
}) {
  const { t } = useTranslation("chat");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleClick = useCallback(
    async (action: MessageActionView) => {
      if (action.kind === "copy") {
        setCopiedId(messageId);
        setTimeout(() => setCopiedId(null), 2000);
      }
      onAction(action.kind, messageId);
    },
    [messageId, onAction],
  );

  if (actions.length === 0) return null;

  return (
    <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
      {actions.map((action) => {
        const label = t(action.labelKey, action.fallback);
        return (
          <button
            key={action.kind}
            type="button"
            onClick={() => handleClick(action)}
            className="inline-flex h-6 items-center gap-1 rounded px-1.5 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
            title={label}
            aria-label={label}
          >
            {action.kind === "copy" && copiedId === messageId ? (
              <span className="text-success">{t("chat:messageActions.copied", "Copied!")}</span>
            ) : (
              <>
                {ACTION_ICONS[action.kind]}
                <span className="hidden sm:inline">{label}</span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}
