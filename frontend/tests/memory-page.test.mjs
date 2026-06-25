import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { test } from "node:test";
import esbuild from "esbuild";

async function renderMemoryContent() {
  const resolveDir = new URL("..", import.meta.url).pathname;
  const result = await esbuild.build({
    absWorkingDir: resolveDir,
    bundle: true,
    format: "cjs",
    platform: "node",
    write: false,
    entryPoints: ["tests/fixtures/render-memory-page.tsx"],
    plugins: [
      {
        name: "memory-page-test-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/components\/shared\/DataTable$/ }, () => ({
            path: "mock-data-table",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/shared\/ConfirmDialog$/ }, () => ({
            path: "mock-confirm-dialog",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/shared\/states$/ }, () => ({
            path: "mock-states",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/badge$/ }, () => ({
            path: "mock-badge",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/button$/ }, () => ({
            path: "mock-button",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/input$/ }, () => ({
            path: "mock-input",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/tabs$/ }, () => ({
            path: "mock-tabs",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@tanstack\/react-query$/ }, () => ({
            path: "mock-react-query",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^react-i18next$/ }, () => ({
            path: "mock-react-i18next",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/lib\/api$/ }, () => ({
            path: "mock-api",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/lib\/host\/HostProvider$/ }, () => ({
            path: "mock-host",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/lib\/utils$/ }, () => ({
            path: "mock-utils",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\// }, (args) => ({
            path: new URL(`../src/${args.path.slice(2)}`, import.meta.url).pathname,
          }));

          build.onLoad({ filter: /^mock-data-table$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function DataTable(props) {
                return React.createElement("section", null, props.empty ?? "table");
              }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-confirm-dialog$/, namespace: "mock" }, () => ({
            contents: "export function ConfirmDialog() { return null; }",
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-states$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function LoadingState(props) { return React.createElement("div", null, props.label ?? "Loading"); }
              export function ErrorState() { return React.createElement("div", null, "Error"); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-badge$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Badge(props) { return React.createElement("span", props, props.children); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-button$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Button(props) { return React.createElement("button", props, props.children); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-input$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export const Input = React.forwardRef((props, ref) => React.createElement("input", { ...props, ref }));
              export const Label = React.forwardRef((props, ref) => React.createElement("label", { ...props, ref }, props.children));
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-tabs$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Tabs(props) { return React.createElement("section", props); }
              export function TabsList(props) { return React.createElement("nav", props); }
              export function TabsTrigger(props) { return React.createElement("button", props); }
              export function TabsContent(props) { return React.createElement("div", props); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-react-query$/, namespace: "mock" }, () => ({
            contents: `
              export function useQuery() {
                return {
                  data: { provider: "mem0", enabled: true },
                  isLoading: false,
                  isError: false,
                  error: null,
                  refetch: () => undefined,
                };
              }
              export function useMutation() {
                return { mutate: () => undefined, isPending: false, isSuccess: false, isError: false, error: null };
              }
              export function useQueryClient() {
                return { invalidateQueries: () => undefined };
              }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-react-i18next$/, namespace: "mock" }, () => ({
            contents: `
              const translations = {
                title: "Memory",
                longTermTitle: "Mem0 long-term memory",
                longTermDescription: "Memory is stored only in Mem0 for cross-thread recall.",
                provider: "Provider",
                status: "Status",
                enabled: "Enabled",
                disabled: "Disabled",
                forgetMemory: "Forget memory",
                forgetMemoryDescription: "Delete a Mem0 memory by id.",
                memoryId: "Memory ID",
                forget: "Forget",
                entries: "Entries",
                candidates: "Candidates",
              };
              export function useTranslation() {
                return { t: (key) => translations[key] ?? key };
              }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-api$/, namespace: "mock" }, () => ({
            contents: `
              export const memoryApi = {
                list: async () => [],
                candidates: async () => [],
              };
              export const longTermMemoryApi = {
                health: async () => ({ provider: "mem0", enabled: true }),
                forget: async () => ({ memory_id: "mem0_1", deleted: true }),
              };
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-host$/, namespace: "mock" }, () => ({
            contents: `
              export function useHost() {
                return { context: { locale: { language: "en" } } };
              }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-utils$/, namespace: "mock" }, () => ({
            contents: `
              export function cn(...classes) { return classes.filter(Boolean).join(" "); }
              export function relativeTime() { return "now"; }
            `,
            loader: "js",
          }));
        },
      },
    ],
  });

  const tmp = await mkdtemp(join(tmpdir(), "aithru-memory-page-"));
  const outFile = join(tmp, "render-memory-page.cjs");
  await writeFile(outFile, result.outputFiles[0].text, "utf8");
  try {
    const require = createRequire(import.meta.url);
    const module = require(outFile);
    return module.default;
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
}

test("memory settings render Mem0 long-term controls instead of local candidates", async () => {
  const html = await renderMemoryContent();

  assert.match(html, /Mem0 long-term memory/);
  assert.match(html, /Provider/);
  assert.match(html, /mem0/);
  assert.match(html, /Forget memory/);
  assert.doesNotMatch(html, /Candidates/);
  assert.doesNotMatch(html, /Entries/);
});
