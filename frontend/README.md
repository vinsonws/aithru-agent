# Aithru Agent Frontend

Platform-hosted Agent UI for `aithru-agent`. This is a **Hosted Subsystem Page**,
not a standalone shell or workflow graph editor (see
`aithru-docs/docs/03-frontend-constraints.md`).

## Stack

- React 19 + TypeScript + Vite 6
- React Router, Tailwind CSS 3 (CSS variables / semantic tokens)
- shadcn/ui + Radix UI primitives, lucide-react icons
- TanStack Query (server state) + TanStack Table (admin lists)
- React Hook Form + Zod, i18next / react-i18next (en-US, zh-CN)
- `react-markdown` + `remark-gfm` + `rehype-highlight` (highlight.js) for chat
  markdown rendering and code highlighting — single component system, no Antd.
- `react-resizable-panels` for the draggable inspection panel.
- Backend types generated from OpenAPI (`src/lib/api/schema.d.ts`).

## Run

The backend has no CORS, so dev uses a Vite proxy:

```bash
# 1. backend (test model for local dev)
cd ../backend
npm run dev

# 2. frontend
cd ../frontend
npm install
npm run dev   # http://localhost:5173 (override backend via AITHRU_AGENT_BACKEND)
```

Set `AITHRU_AGENT_BACKEND` if the backend is not at `http://127.0.0.1:8000`.

## Scripts

```bash
npm run dev          # vite dev server (proxies /api to backend)
npm run build        # tsc + vite build
npm run typecheck    # tsc -b --noEmit
npm run gen:types    # regenerate src/lib/api/schema.d.ts from OpenAPI
```

To regenerate types after backend schema changes:

```bash
cd ../frontend
# Refresh openapi.json from the TypeScript backend export when available.
npx openapi-typescript ./openapi.json -o src/lib/api/schema.d.ts
```

## Architecture

Three-pane hosted subsystem layout (see `../frontend-prototype-design.md`):

- **Left** — collapsible session nav: thread dashboard list, new thread,
  Skills / Approvals / Memory / Settings.
- **Center** — conversation (lobe-ui Markdown + tool-call cards + inline
  approval/input request cards + composer with skill/model-profile selection).
  `useRunStream` projects backend `AgentStreamEvent` SSE into chat state.
- **Right** — `DraggablePanel` inspection, default-collapsed to a status/todo
  rail; expands to Run / Workspace / Artifacts / Approvals / Memory tabs.

### Key boundaries

- **Security**: access token in memory only; identity via trusted
  `X-Aithru-Org-Id` / `X-Aithru-User-Id` headers bound by the backend; browser
  storage holds only non-sensitive UI preferences (sidebar/panel collapse, dev
  locale/theme). No token/secret in localStorage/sessionStorage/URL/UI.
- **Host bridge**: `AITHRU_HOST_INIT` / `AITHRU_HOST_CONTEXT_CHANGED` provide
  `runtimeContext` (theme.resolved, locale, org, user). Production hosted mode
  never persists independent theme/locale; local mock mode exposes dev
  controls.
- **Browser is not the security authority** — the backend enforces identity,
  grants, capability routing, approval, audit, and redaction.

## Decisions (locked)

- D1 component boundary = restricted mixing (lobe-ui only in intelligent area)
- D2 inspection panel = draggable, default-collapsed
- D3 MVP = full, including admin pages
- D4 thread list vs focus = same-page sidebar switching
