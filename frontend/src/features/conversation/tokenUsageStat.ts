export interface TokenUsageCounters {
  input?: number | null;
  output?: number | null;
  total?: number | null;
}

export interface TokenUsageDisplay {
  summary: string;
  input: string;
  output: string;
  total: string;
}

export function buildTokenUsageDisplay(
  usage?: TokenUsageCounters | null,
): TokenUsageDisplay | null {
  const input = normalizeCounter(usage?.input);
  const output = normalizeCounter(usage?.output);
  const providedTotal = normalizeCounter(usage?.total);
  const computedTotal =
    providedTotal ?? (input != null || output != null ? (input ?? 0) + (output ?? 0) : null);

  if (input == null && output == null && computedTotal == null) {
    return null;
  }

  return {
    summary: formatTokenCount(computedTotal ?? input ?? output),
    input: formatTokenCount(input),
    output: formatTokenCount(output),
    total: formatTokenCount(computedTotal),
  };
}

export function formatTokenCount(value: number | null | undefined): string {
  if (value == null) return "-";

  const rounded = Math.max(0, Math.round(value));
  if (rounded >= 10_000) {
    const thousands = rounded / 1_000;
    const precision = thousands >= 100 ? 0 : 1;
    return `${trimTrailingZero(thousands.toFixed(precision))}K`;
  }

  return rounded.toLocaleString("en-US");
}

function normalizeCounter(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }
  return value;
}

function trimTrailingZero(value: string): string {
  return value.endsWith(".0") ? value.slice(0, -2) : value;
}
