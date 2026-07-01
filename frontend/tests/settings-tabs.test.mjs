import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function renderSettingsTabs() {
  const resolveDir = fileURLToPath(new URL("..", import.meta.url));
  const result = await esbuild.build({
    absWorkingDir: resolveDir,
    bundle: true,
    format: "cjs",
    platform: "node",
    write: false,
    entryPoints: ["tests/fixtures/render-settings-tabs.tsx"],
    plugins: [
      {
        name: "settings-tabs-test-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/features\/admin\/ModelProfilesPage$/ }, () => ({
            path: "mock-model-profiles",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/admin\/ExternalToolsPage$/ }, () => ({
            path: "mock-external-tools",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/admin\/SkillsPage$/ }, () => ({
            path: "mock-skills",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/admin\/ApprovalsPage$/ }, () => ({
            path: "mock-approvals",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/admin\/MemoryPage$/ }, () => ({
            path: "mock-memory",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/tabs$/ }, () => ({
            path: "mock-tabs",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/dialog$/ }, () => ({
            path: "mock-dialog",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/badge$/ }, () => ({
            path: "mock-badge",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/separator$/ }, () => ({
            path: "mock-separator",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/scroll-area$/ }, () => ({
            path: "mock-scroll-area",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/shared\/states$/ }, () => ({
            path: "mock-states",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^react-i18next$/ }, () => ({
            path: "mock-react-i18next",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@tanstack\/react-query$/ }, () => ({
            path: "mock-react-query",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/lib\/api$/ }, () => ({
            path: "mock-api",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/lib\/utils$/ }, () => ({
            path: "mock-utils",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\// }, (args) => ({
            path: fileURLToPath(new URL(`../src/${args.path.slice(2)}`, import.meta.url)),
          }));

          build.onLoad({ filter: /^mock-model-profiles$/, namespace: "mock" }, () => ({
            contents: "export function ModelProfilesContent() { return null; }",
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-external-tools$/, namespace: "mock" }, () => ({
            contents: "export function ExternalToolsContent() { return null; }",
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-skills$/, namespace: "mock" }, () => ({
            contents: "export function SkillsContent() { return null; }",
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-approvals$/, namespace: "mock" }, () => ({
            contents: "export function ApprovalsContent() { return null; }",
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-memory$/, namespace: "mock" }, () => ({
            contents: "export function MemoryContent() { return null; }",
            loader: "js",
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
          build.onLoad({ filter: /^mock-dialog$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Dialog(props) { return React.createElement("div", props); }
              export function DialogContent(props) { return React.createElement("div", props); }
              export function DialogDescription(props) { return React.createElement("p", props); }
              export function DialogHeader(props) { return React.createElement("header", props); }
              export function DialogTitle(props) { return React.createElement("h2", props); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-scroll-area$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function ScrollArea(props) { return React.createElement("div", props); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-badge$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Badge(props) { return React.createElement("span", props); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-separator$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Separator(props) { return React.createElement("hr", props); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-states$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function LoadingState(props) { return React.createElement("div", props, props.label); }
              export function ErrorState() { return React.createElement("div", null, "Error"); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-react-i18next$/, namespace: "mock" }, () => ({
            contents: `
              const translations = {
                title: "Settings",
                modelProfiles: "Model profiles",
                externalTools: "External tools",
                skills: "Skills",
                memory: "Memory",
                memoryDescription: "Review the long-term memory provider.",
                runtime: "Runtime",
                runtimeDefaults: "Runtime defaults",
                runtimeDefaultsDescription: "Startup environment values are read-only here.",
                backendHealth: "Backend health",
                managedConfiguration: "Managed configuration",
                restartRequired: "Restart required",
                liveConfig: "Live",
                service: "Service",
              };
              export function useTranslation() {
                return { t: (key) => translations[key] ?? key };
              }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-react-query$/, namespace: "mock" }, () => ({
            contents: `
              export function useQuery() {
                return {
                  data: { ok: true, service: "aithru-agent-backend" },
                  isLoading: false,
                  isError: false,
                  error: null,
                  refetch: () => undefined,
                };
              }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-api$/, namespace: "mock" }, () => ({
            contents: `
              export const healthApi = {
                check: async () => ({ ok: true, service: "aithru-agent-backend" }),
              };
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-utils$/, namespace: "mock" }, () => ({
            contents: `
              export function cn(...classes) {
                return classes.filter(Boolean).join(" ");
              }
            `,
            loader: "js",
          }));
        },
      },
    ],
  });

  const tmp = await mkdtemp(join(tmpdir(), "aithru-settings-tabs-"));
  const outFile = join(tmp, "render-settings-tabs.cjs");
  await writeFile(outFile, result.outputFiles[0].text, "utf8");
  try {
    const require = createRequire(import.meta.url);
    const module = require(outFile);
    return module.default;
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
}

test("settings tabs expose product-managed configuration and runtime defaults", async () => {
  const html = await renderSettingsTabs();

  assert.match(html, /Model profiles/);
  assert.match(html, /External tools/);
  assert.match(html, /Skills/);
  assert.match(html, /Memory/);
  assert.equal((html.match(/Review the long-term memory provider/g) ?? []).length, 1);
  assert.match(html, /Runtime/);
  assert.match(html, /Runtime defaults/);
  assert.match(html, /Backend health/);
  assert.match(html, /Managed configuration/);
  assert.match(html, /Restart required/);
});
