import { spawn } from "node:child_process";
import { resolve, sep } from "node:path";

export type SandboxRuntime = "auto" | "bash" | "node";
export type ResolvedSandboxRuntime = Exclude<SandboxRuntime, "auto">;

export interface SandboxExecutorOptions {
  workspaceRoot: string;
  envAllowlist?: readonly string[];
  defaultTimeoutMs?: number;
  defaultMaxOutputBytes?: number;
}

export interface SandboxExecutionRequest {
  runtime: SandboxRuntime;
  command?: string;
  code?: string;
  cwd?: string;
  timeoutMs?: number;
  maxOutputBytes?: number;
  env?: Record<string, string | undefined>;
}

export interface SandboxExecutionResult {
  runtime: ResolvedSandboxRuntime;
  stdout: string;
  stderr: string;
  exitCode: number;
  truncated: boolean;
  timedOut: boolean;
}

interface StreamState {
  stdout: Buffer[];
  stderr: Buffer[];
  remainingBytes: number;
  truncated: boolean;
}

const DEFAULT_TIMEOUT_MS = 30_000;
const MAX_TIMEOUT_MS = 120_000;
const DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024;

export class SandboxExecutor {
  private readonly workspaceRoot: string;
  private readonly envAllowlist: readonly string[];
  private readonly defaultTimeoutMs: number;
  private readonly defaultMaxOutputBytes: number;

  constructor(options: SandboxExecutorOptions) {
    this.workspaceRoot = resolve(options.workspaceRoot);
    this.envAllowlist = options.envAllowlist ?? [];
    this.defaultTimeoutMs = clampTimeout(options.defaultTimeoutMs ?? DEFAULT_TIMEOUT_MS);
    this.defaultMaxOutputBytes = clampOutputLimit(
      options.defaultMaxOutputBytes ?? DEFAULT_MAX_OUTPUT_BYTES,
    );
  }

  async execute(request: SandboxExecutionRequest): Promise<SandboxExecutionResult> {
    const source = request.code ?? request.command;
    if (!source || (request.code && request.command)) {
      throw new Error("Provide exactly one of code or command.");
    }

    const runtime = resolveRuntime(request);
    const cwd = resolveWorkspaceCwd(this.workspaceRoot, request.cwd);
    const timeoutMs = clampTimeout(request.timeoutMs ?? this.defaultTimeoutMs);
    const maxOutputBytes = clampOutputLimit(
      request.maxOutputBytes ?? this.defaultMaxOutputBytes,
    );
    const child = spawn(...spawnArgs(runtime, source), {
      cwd,
      env: buildEnv(this.envAllowlist, request.env),
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });

    return await new Promise((resolveResult, reject) => {
      const streams: StreamState = {
        stdout: [],
        stderr: [],
        remainingBytes: maxOutputBytes,
        truncated: false,
      };
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        child.kill("SIGKILL");
      }, timeoutMs);

      child.once("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });

      child.stdout.on("data", (chunk: Buffer) => appendChunk(streams, "stdout", chunk));
      child.stderr.on("data", (chunk: Buffer) => appendChunk(streams, "stderr", chunk));

      child.once("close", (exitCode) => {
        clearTimeout(timer);
        resolveResult({
          runtime,
          stdout: Buffer.concat(streams.stdout).toString("utf8"),
          stderr: Buffer.concat(streams.stderr).toString("utf8"),
          exitCode: exitCode ?? (timedOut ? 124 : 1),
          truncated: streams.truncated,
          timedOut,
        });
      });
    });
  }
}

function resolveRuntime(request: SandboxExecutionRequest): ResolvedSandboxRuntime {
  if (request.runtime !== "auto") {
    return request.runtime;
  }
  return request.code ? "node" : "bash";
}

function resolveWorkspaceCwd(workspaceRoot: string, cwd?: string): string {
  const resolved = resolve(workspaceRoot, cwd ?? ".");
  if (resolved !== workspaceRoot && !resolved.startsWith(`${workspaceRoot}${sep}`)) {
    throw new Error("cwd must stay within workspaceRoot");
  }
  return resolved;
}

function buildEnv(
  allowlist: readonly string[],
  env: Record<string, string | undefined> | undefined,
): Record<string, string> {
  const nextEnv: Record<string, string> = {};
  if (process.env.PATH) {
    nextEnv.PATH = process.env.PATH;
  }

  for (const key of allowlist) {
    const value = env?.[key] ?? process.env[key];
    if (value !== undefined) {
      nextEnv[key] = value;
    }
  }

  return nextEnv;
}

function spawnArgs(
  runtime: ResolvedSandboxRuntime,
  source: string,
): [command: string, args: string[]] {
  switch (runtime) {
    case "bash":
      return ["bash", ["-lc", source]];
    case "node":
      return [process.execPath, ["--input-type=module", "--eval", source]];
  }
}

function appendChunk(
  streams: StreamState,
  target: "stdout" | "stderr",
  chunk: Buffer,
): void {
  if (chunk.length === 0) {
    return;
  }

  if (streams.remainingBytes <= 0) {
    streams.truncated = true;
    return;
  }

  const slice = chunk.subarray(0, streams.remainingBytes);
  streams[target].push(slice);
  streams.remainingBytes -= slice.length;
  if (slice.length < chunk.length) {
    streams.truncated = true;
  }
}

function clampTimeout(timeoutMs: number): number {
  return Math.min(MAX_TIMEOUT_MS, Math.max(1, Math.trunc(timeoutMs)));
}

function clampOutputLimit(maxOutputBytes: number): number {
  return Math.max(0, Math.trunc(maxOutputBytes));
}
