import type {
  AgentError,
  AgentResearchFinding,
  AgentResearchOptions,
  AgentResearchReport,
  AgentResearchSource,
} from "@aithru/agent-core";
import { isObject } from "../utils.js";

export type ResearchCollection = {
  sources: AgentResearchSource[];
  findings: AgentResearchFinding[];
  notes: string[];
};

export function createResearchCollection(): ResearchCollection {
  return {
    sources: [],
    findings: [],
    notes: [],
  };
}

export function boundedCount(value: number | undefined, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }

  return Math.max(0, Math.floor(value));
}

export function collectResearchOutput(
  collection: ResearchCollection,
  value: unknown,
): void {
  if (value === undefined) {
    return;
  }

  if (typeof value === "string") {
    collection.notes.push(value);
    return;
  }

  if (!isObject(value)) {
    return;
  }

  if (isResearchSourceLike(value)) {
    addResearchSource(collection, value);
  }

  if (isResearchFindingLike(value)) {
    addResearchFinding(collection, value);
  }

  if (Array.isArray(value.sources)) {
    for (const source of value.sources) {
      addResearchSource(collection, source);
    }
  }

  if (isObject(value.source)) {
    addResearchSource(collection, value.source);
  }

  if (Array.isArray(value.findings)) {
    for (const finding of value.findings) {
      addResearchFinding(collection, finding);
    }
  }

  if (isObject(value.finding)) {
    addResearchFinding(collection, value.finding);
  }

  if (typeof value.summary === "string") {
    collection.notes.push(value.summary);
  }
}

function addResearchSource(
  collection: ResearchCollection,
  value: unknown,
): void {
  const source = normalizeResearchSource(value, collection.sources.length);
  if (!collection.sources.some((existing) => existing.id === source.id)) {
    collection.sources.push(source);
  }
}

function addResearchFinding(
  collection: ResearchCollection,
  value: unknown,
): void {
  const finding = normalizeResearchFinding(value, collection.findings.length);
  if (!collection.findings.some((existing) => existing.id === finding.id)) {
    collection.findings.push(finding);
  }
}

function isResearchSourceLike(value: Record<string, unknown>): boolean {
  return (
    typeof value.id === "string" ||
    typeof value.uri === "string" ||
    Object.prototype.hasOwnProperty.call(value, "content")
  );
}

function isResearchFindingLike(value: Record<string, unknown>): boolean {
  return typeof value.claim === "string";
}

function normalizeResearchSource(
  value: unknown,
  index: number,
): AgentResearchSource {
  if (isObject(value)) {
    return {
      id: typeof value.id === "string" ? value.id : `source_${index + 1}`,
      ...(typeof value.title === "string" ? { title: value.title } : {}),
      ...(typeof value.uri === "string" ? { uri: value.uri } : {}),
      ...(Object.prototype.hasOwnProperty.call(value, "content")
        ? { content: value.content }
        : {}),
      ...(isObject(value.metadata) ? { metadata: value.metadata } : {}),
    };
  }

  return {
    id: `source_${index + 1}`,
    content: value,
  };
}

function normalizeResearchFinding(
  value: unknown,
  index: number,
): AgentResearchFinding {
  if (isObject(value)) {
    return {
      id: typeof value.id === "string" ? value.id : `finding_${index + 1}`,
      claim:
        typeof value.claim === "string"
          ? value.claim
          : typeof value.summary === "string"
            ? value.summary
            : "Research finding.",
      ...(Array.isArray(value.sourceIds)
        ? {
            sourceIds: value.sourceIds.filter(
              (sourceId): sourceId is string => typeof sourceId === "string",
            ),
          }
        : {}),
      ...(typeof value.confidence === "number"
        ? { confidence: value.confidence }
        : {}),
      ...(isObject(value.metadata) ? { metadata: value.metadata } : {}),
    };
  }

  return {
    id: `finding_${index + 1}`,
    claim: String(value ?? "Research finding."),
  };
}

export function normalizeResearchReport(
  taskGoal: string,
  value: unknown,
  collection: ResearchCollection,
  options: AgentResearchOptions | undefined,
): AgentResearchReport {
  const reportValue = isObject(value) ? value : undefined;
  const sources =
    reportValue && Array.isArray(reportValue.sources)
      ? reportValue.sources.map((source: unknown, index: number) =>
          normalizeResearchSource(source, index),
        )
      : collection.sources;
  const findings =
    reportValue && Array.isArray(reportValue.findings)
      ? reportValue.findings.map((finding: unknown, index: number) =>
          normalizeResearchFinding(finding, index),
        )
      : collection.findings;
  const boundedSources = limitResearchSources(sources, options?.maxSources);
  const boundedFindings = alignFindingSourceIds(findings, boundedSources);
  const summary =
    reportValue && typeof reportValue.summary === "string"
      ? reportValue.summary
      : typeof value === "string"
        ? value
        : (collection.notes.at(-1) ?? "Research completed.");

  return {
    title:
      reportValue && typeof reportValue.title === "string"
        ? reportValue.title
        : taskGoal,
    summary,
    findings: boundedFindings,
    sources: boundedSources,
    ...(reportValue && Array.isArray(reportValue.limitations)
      ? {
          limitations: reportValue.limitations.filter(
            (limitation: unknown): limitation is string =>
              typeof limitation === "string",
          ),
        }
      : {}),
    ...(reportValue && isObject(reportValue.metadata)
      ? { metadata: reportValue.metadata }
      : {}),
  };
}

function limitResearchSources(
  sources: AgentResearchSource[],
  maxSources: number | undefined,
): AgentResearchSource[] {
  if (typeof maxSources !== "number" || !Number.isFinite(maxSources)) {
    return sources;
  }

  return sources.slice(0, Math.max(0, Math.floor(maxSources)));
}

function alignFindingSourceIds(
  findings: AgentResearchFinding[],
  sources: AgentResearchSource[],
): AgentResearchFinding[] {
  const sourceIds = new Set(sources.map((source) => source.id));

  return findings.map((finding) => {
    if (!finding.sourceIds) {
      return finding;
    }

    return {
      ...finding,
      sourceIds: finding.sourceIds.filter((sourceId) =>
        sourceIds.has(sourceId),
      ),
    };
  });
}

export function researchTimeoutError(timeoutMs: number): AgentError {
  return {
    code: "research_timeout",
    message: `Deep Research exceeded timeoutMs (${timeoutMs}).`,
  };
}

export function extractResearchCollection(
  resumeState: { metadata?: Record<string, unknown> },
): ResearchCollection {
  const raw = resumeState.metadata?.researchCollection;
  if (
    raw &&
    typeof raw === "object" &&
    Array.isArray((raw as Record<string, unknown>).sources) &&
    Array.isArray((raw as Record<string, unknown>).findings) &&
    Array.isArray((raw as Record<string, unknown>).notes)
  ) {
    return raw as ResearchCollection;
  }
  return createResearchCollection();
}
