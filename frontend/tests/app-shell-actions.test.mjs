import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const appShellPath = new URL("../src/AppShell.tsx", import.meta.url);
const conversationPagePath = new URL("../src/features/conversation/ConversationPage.tsx", import.meta.url);
const conversationHeaderPath = new URL("../src/features/conversation/ConversationHeader.tsx", import.meta.url);
const sidebarPath = new URL("../src/features/sidebar/Sidebar.tsx", import.meta.url);
const rightRailPath = new URL("../src/features/sidebar/RightRail.tsx", import.meta.url);

test("manager dialogs wrap both sidebar and conversation routes", async () => {
  const source = await readFile(appShellPath, "utf8");
  const managerStart = source.indexOf("<ManagerDialogs>");
  const sidebarIndex = source.indexOf("<Sidebar", managerStart);
  const routeIndex = source.indexOf("<RouteContent", managerStart);
  const managerEnd = source.indexOf("</ManagerDialogs>", managerStart);

  assert.ok(managerStart >= 0, "AppShell should render ManagerDialogs");
  assert.ok(sidebarIndex > managerStart, "Sidebar should be inside ManagerDialogs");
  assert.ok(routeIndex > sidebarIndex, "RouteContent should be inside ManagerDialogs");
  assert.ok(managerEnd > routeIndex, "ManagerDialogs should close after RouteContent");
});

test("open model settings action uses the manager dialog API", async () => {
  const source = await readFile(conversationPagePath, "utf8");

  assert.match(source, /useManager/);
  assert.match(source, /manager\.open\("settings"\)/);
  assert.doesNotMatch(source, /aithru:open-settings/);
});

test("sidebar footer only exposes approvals and settings manager entries", async () => {
  const source = await readFile(sidebarPath, "utf8");

  assert.match(source, /open\("approvals"\)/);
  assert.match(source, /open\("settings"\)/);
  assert.doesNotMatch(source, /open\("skills"\)/);
  assert.doesNotMatch(source, /open\("memory"\)/);
  assert.doesNotMatch(source, /<Separator/);
});

test("sidebar brand uses an unframed robot avatar", async () => {
  const source = await readFile(sidebarPath, "utf8");
  const avatarMatch = source.match(/data-testid="sidebar-brand-avatar"[^>]+className="([^"]+)"/);

  assert.match(source, /\bBot,\n/);
  assert.match(source, /<Bot className="h-4 w-4"/);
  assert.ok(avatarMatch, "Sidebar brand avatar should be easy to target");
  assert.doesNotMatch(avatarMatch?.[1] ?? "", /\bborder\b/);
  assert.doesNotMatch(source, /MessagesSquare/);
});

test("conversation header keeps only primary conversation controls visible", async () => {
  const source = await readFile(conversationHeaderPath, "utf8");

  assert.match(source, /StatusChip/);
  assert.match(source, /view\.actions\.map/);
  assert.doesNotMatch(source, /view\.subline/);
  assert.doesNotMatch(source, /view\.modelLabel/);
  assert.doesNotMatch(source, /view\.permissionLabel/);
});

test("conversation header no longer owns the inspection rail toggle", async () => {
  const headerSource = await readFile(conversationHeaderPath, "utf8");

  // The inspection toggle has been removed from ConversationHeader;
  // panel toggling now lives in the RightRail component in AppShell.
  assert.doesNotMatch(headerSource, /onToggleInspection/);
  assert.doesNotMatch(headerSource, /PanelRightOpen/);
  assert.doesNotMatch(headerSource, /PanelRightClose/);
});

test("conversation page does not render the top task strip", async () => {
  const source = await readFile(conversationPagePath, "utf8");

  assert.doesNotMatch(source, /RunGoalBar/);
  assert.doesNotMatch(source, /buildRunTaskLoopView/);
});

test("conversation page wires right panel and file preview callbacks instead of inspection panel", async () => {
  const source = await readFile(conversationPagePath, "utf8");

  // No longer passes inspection props to ConversationHeader
  assert.doesNotMatch(source, /inspectionCollapsed/);
  assert.doesNotMatch(source, /inspectionPanel/);
  // Uses new right-panel callbacks
  assert.match(source, /onOpenRightPanel/);
  assert.match(source, /onPreviewFile/);
  assert.match(source, /<div className="flex min-h-0 flex-1">/);
});

test("initial page does not render the inspection panel", async () => {
  const source = await readFile(appShellPath, "utf8");
  const conversationRoute = source.slice(source.indexOf("function ConversationRoute"));
  const noThreadBranch = conversationRoute.match(/if \(!threadId\) \{[\s\S]+?\n  \}/)?.[0] ?? "";

  assert.match(noThreadBranch, /return <NewThreadPage \/>/);
  assert.doesNotMatch(noThreadBranch, /inspectionPanel/);
});

test("collapsed rail uses the same quiet surface as surrounding chrome", async () => {
  const source = await readFile(rightRailPath, "utf8");
  const collapsedClass = source.match(/"hidden w-12[^"]+"/)?.[0] ?? "";

  assert.match(collapsedClass, /border-border\/70/);
  assert.match(collapsedClass, /bg-background/);
  assert.doesNotMatch(collapsedClass, /bg-card/);
  assert.doesNotMatch(source, /bg-warning\/\[/);
});

test("right panel toggle sets panel id and clears on double-click", async () => {
  const source = await readFile(rightRailPath, "utf8");

  // RightRail exposes an onClick that toggles: active → null, inactive → id
  assert.match(source, /onPanelChange\(isActive \? null : item\.id\)/);

  // Active state is determined by comparing activePanel to item.id
  assert.match(source, /isActive\s*=\s*activePanel\s*===\s*item\.id/);
});

test("right panel is stored as session-only React state in AppShell", async () => {
  const source = await readFile(appShellPath, "utf8");

  // rightPanel uses React.useState, not localStorage
  assert.match(
    source,
    /const \[rightPanel,\s*setRightPanel\]\s*=\s*React\.useState<string\s*\|\s*null\s*>\s*\(null\)/,
  );

  // RouteContent wires setRightPanel as onRightPanelChange
  assert.match(source, /onRightPanelChange=\{setRightPanel\}/);
});
