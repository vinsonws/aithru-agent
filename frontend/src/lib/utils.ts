import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format an ISO timestamp using the resolved locale + runtime time zone. */
export function formatDateTime(
  iso: string | null | undefined,
  locale: string,
  timeZone: string,
): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: "short",
      timeStyle: "short",
      timeZone,
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function relativeTime(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  const diff = new Date(iso).getTime() - Date.now();
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const abs = Math.abs(diff);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["second", 1000],
    ["minute", 60_000],
    ["hour", 3_600_000],
    ["day", 86_400_000],
    ["week", 604_800_000],
  ];
  let unit: Intl.RelativeTimeFormatUnit = "second";
  let value = diff;
  for (const [u, ms] of units) {
    if (abs < ms) break;
    unit = u;
    value = Math.round(diff / ms);
  }
  return rtf.format(value, unit);
}
