import * as React from "react";
import { AlertTriangle, Ban, FileQuestion, Inbox, Loader2, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin text-muted-foreground", className)} />;
}

export function LoadingState({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-muted-foreground">
      <Spinner className="h-5 w-5" />
      <span className="text-sm">{label ?? t("common:loading", { defaultValue: "Loading…" })}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-muted-foreground">
      {icon ?? <Inbox className="h-8 w-8 opacity-60" />}
      <p className="text-sm font-medium text-foreground">
        {title ?? t("common:empty", { defaultValue: "Nothing here yet" })}
      </p>
      {description && <p className="max-w-xs text-xs">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const { t } = useTranslation();
  const apiErr = error instanceof ApiError ? error : undefined;
  const message = apiErr?.code
    ? t(`errors:${apiErr.code}`, { defaultValue: apiErr.message })
    : apiErr?.message ?? t("common:errorGeneric", { defaultValue: "Something went wrong" });

  if (apiErr?.status === 403) return <PermissionDeniedState />;

  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <AlertTriangle className="h-8 w-8 text-destructive" />
      <div>
        <p className="text-sm font-medium">{message}</p>
        {apiErr?.requestId && (
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            {t("common:requestId", { defaultValue: "Request" })}: {apiErr.requestId}
          </p>
        )}
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          {t("common:retry", { defaultValue: "Retry" })}
        </Button>
      )}
    </div>
  );
}

export function PermissionDeniedState() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-muted-foreground">
      <Lock className="h-8 w-8 text-warning" />
      <p className="text-sm font-medium text-foreground">
        {t("common:permissionDenied", { defaultValue: "Permission denied" })}
      </p>
      <p className="max-w-xs text-xs">
        {t("common:permissionDeniedHint", {
          defaultValue: "You do not have access to this resource.",
        })}
      </p>
    </div>
  );
}

export function NotFoundState({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-muted-foreground">
      <FileQuestion className="h-8 w-8 opacity-60" />
      <p className="text-sm font-medium text-foreground">
        {label ?? t("common:notFound", { defaultValue: "Not found" })}
      </p>
    </div>
  );
}

export function CancelledState({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-muted-foreground">
      <Ban className="h-4 w-4" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
