import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Displays a value that may be sensitive (secrets, tokens, connection strings).
 * Defaults to redacted; user must explicitly reveal. Never used for actual
 * access tokens / refresh tokens (those are never sent to the browser).
 */
export function RedactedValue({
  value,
  className,
  revealLabel = "Reveal",
  hideLabel = "Hide",
  monospace = true,
}: {
  value: string;
  className?: string;
  revealLabel?: string;
  hideLabel?: string;
  monospace?: boolean;
}) {
  const [revealed, setRevealed] = React.useState(false);
  const masked = "•".repeat(Math.min(value.length, 16)) || "••••";
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <span className={cn(monospace && "font-mono text-xs")}>{revealed ? value : masked}</span>
      <button
        type="button"
        onClick={() => setRevealed((v) => !v)}
        className="inline-flex h-5 items-center rounded px-1 text-muted-foreground hover:text-foreground"
        aria-label={revealed ? hideLabel : revealLabel}
      >
        {revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      </button>
    </span>
  );
}

export function RedactedCell({ present }: { present: boolean }) {
  return present ? (
    <span className="font-mono text-xs text-muted-foreground">••••••••</span>
  ) : (
    <span className="text-xs text-muted-foreground">—</span>
  );
}
