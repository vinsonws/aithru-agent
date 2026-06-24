# Aithru Agent Frontend Prototype Design

> 状态：原型提案，决策已落定。
> 约束来源：`aithru-docs/docs/03-frontend-constraints.md`、`01/02/04`。
> 智能组件来源：`lobehub/lobe-ui`（基于 Antd，仅用于 Agent 智能交互区）。
>
> 已拍板决策：
> - **D1 组件边界 = 受限混用**：lobe-ui 仅用于智能交互区（聊天气泡/Markdown/代码高亮/思考块/
>   工具调用卡/输入区），其余全部 shadcn/ui+Radix；用 Antd `ConfigProvider` 桥接 Aithru 语义
>   token 保证视觉一致。
> - **D2 检查面板 = 可拖拽分栏 + 默认收起**：默认收成右侧窄条，只显示运行状态/Todo 进度，
>   展开后才显示完整 Tabs 检查内容；用 lobe-ui `DraggablePanel` 承载分栏。
> - **D3 MVP 范围 = 全量含管理页**：首期即含对话核心、运行检查、Skills、Memory、Approvals、
>   Model Profile / External Tool 设置页。
> - **D4 列表与聚焦 = 同页侧栏切换**：左栏常驻会话列表，点选即在同页把对话区+检查面板切到
>   该会话，路由 `/threads/:id`。

## 0. 定位与硬约束

Agent 前端是 **Platform 托管的 Hosted Subsystem Page**，不是独立 shell，不是 workflow
graph editor（`03-frontend-constraints.md` 第 13、76–108 行；AGENTS.md Frontend Rules）。

必须遵守的约束：

- **宿主关系**：Platform 拥有全局 chrome（顶栏、账号、org/app 切换、主题、语言、Admin 入口、
  会话恢复）。Agent 前端只拥有「自己的页面区域内」的侧栏 / 标签 / 工具栏 / 过滤器。
  不渲染自己的持久顶栏、app header、全宽全局导航，不复制账号/org/语言/主题/登出控件。
- **运行时上下文**：通过 `AITHRU_HOST_INIT` 接收初始 `runtimeContext`（`theme.resolved`、
  `locale.language`、`locale.timeZone`、org、user、route、permission），通过
  `AITHRU_HOST_CONTEXT_CHANGED` 响应变化。不独立持久化全局主题/语言偏好（开发/mock 模式可
  暴露调试开关，生产隐藏）。
- **技术栈**：React 19 + TS + Vite 6 + React Router + Tailwind 3(CSS 变量) + shadcn/ui +
  Radix + lucide-react + TanStack Query/Table + React Hook Form + Zod + i18next/react-i18next。
  不得引入第二套主框架/样式/查询/表格/表单/i18n 体系（`03` 第 15–34 行）。
- **lobe-ui 边界**：lobe-ui 基于 Antd。约束文档要求的是 shadcn/ui + Radix，没有 Antd。
  因此 **lobe-ui 只用于「智能交互区」**（聊天气泡、Markdown 渲染、代码高亮、思考块、工具调用
  展示、流式加载等 AIGC 专有形态），且需在 `ConfigProvider`/`ThemeProvider` 上做主题桥接，
  让 lobe-ui 的 Antd 实例消费 Aithru 语义 token。**非智能 UI 一律用 shadcn/ui**。这是一个需要
  你拍板的混用决策（见决策点 D1）。
- **安全**：access token 仅存内存；refresh token 走 `AITHRU_REFRESH` HttpOnly cookie；
  浏览器存储只放非敏感偏好（主题/locale/最近 org/app/侧栏折叠态）。不把任何 token/secret
  放 localStorage/sessionStorage/URL/可见 UI（`03` 第 272–287 行）。
- **浏览器不是安全权威**：前端只 display/request/inspect/recover/route；后端强制身份/授权/
  审计（`02` Browser Authority）。
- **视觉**：Aithru Slate Intelligence —— 净白浅色画布 + 暖灰分层、Indigo 主操作、Cyan 智能高亮、
  显式状态色。深色为深石板灰，非纯黑。状态不得仅靠颜色传达，必须有文字/图标。
  组件消费语义类：`bg-background`/`bg-card`/`bg-muted`/`text-foreground`/`text-muted-foreground`/
  `border-border`/`bg-primary`/`text-primary`/`text-success`/`text-warning`/`text-destructive`
  （`03` 第 289–337 行）。

## 1. 信息架构（页面结构）

采用「左会话列表 + 中对话区 + 右检查面板」三栏，对应后端的 Thread / Run-Stream / Inspection
三组能力。左、右栏均可折叠（约束第 87 行要求桌面+移动皆可折叠）。

```
┌──────────────────────────────────────────────────────────────────────┐
│  （Platform 全局顶栏，由宿主提供，Agent 前端不渲染）                       │
├────────────┬───────────────────────────────────┬─────────────────────┤
│ 会话/导航   │  对话区（lobe-ui 智能区）           │  检查面板            │
│ 侧栏        │                                   │  DraggablePanel     │
│ (shadcn)    │  ChatHeader / ChatList / 输入      │  默认收起窄条:        │
│             │                                   │   运行状态+Todo进度  │
│ + 新建会话  │  lobe-ui ChatList                  │  ─────────────      │
│ 会话列表    │   ├ user 气泡                      │  展开后 Tabs:        │
│ (dashboard, │   ├ assistant 气泡 + 思考块         │   运行 / 工作区 /    │
│  同页切换)  │   ├ 工具调用卡                     │   制品 / 审批 / 记忆  │
│             │   └ 输入请求 / 审批请求 inline      │  (shadcn)           │
│ Skills      │  ChatInputArea (MessageInput)      │                     │
│ Approvals   │   技能选择 / 模型profile / 发送     │                     │
│ Memory      │                                   │                     │
│ Settings    │                                   │                     │
└────────────┴───────────────────────────────────┴─────────────────────┘
```

页面/路由（React Router，挂在宿主给出的 base path 下）：

| 路由 | 内容 | 后端 API |
| --- | --- | --- |
| `/` 重定向到最近会话或 `/threads` | — | `GET /api/threads/dashboard` |
| `/threads/:threadId` | **同页**：左栏会话列表 + 中对话区 + 右检查面板，点选切换 | `GET /api/threads`, `POST /api/threads`, `/dashboard`, `/messages`, `/workbench` |
| `/threads/:threadId/runs/:runId` | 把右检查面板聚焦到某次 run | `GET /api/runs/{id}/snapshot` |
| `/skills` | 技能包浏览/配置（全量 MVP） | `GET /api/skills`, `GET/POST/PATCH /api/skill-registry` |
| `/approvals` | 待审批队列 | `GET /api/approvals`, `POST .../resolve` |
| `/memory` | 记忆条目 + 候选审批 | `GET /api/memory`, `GET /api/memory-candidates` |
| `/settings/model-profiles` | 模型配置（Admin/Ops 形态） | `GET/POST/PATCH /api/model-profiles` |
| `/settings/external-tools` | 外部工具/MCP 配置 | `/api/external-tools/configs` |

> 会话列表是左栏常驻的一部分（D4 同页切换），不是独立列表页。所有页面共用一个可折叠侧栏 +
> Hosted Subsystem 页面工具栏；不出现独立顶栏。

## 2. 三栏详细设计

### 2.1 左侧栏 — 会话与导航（shadcn/ui）

- **顶部**：「+ 新建会话」主操作（`bg-primary` Indigo）。点击弹一个轻量目标输入 →
  `POST /api/threads` + `POST /api/runs`（带 `goal`、可选 `skill_id`、`harness_options`）。
- **会话列表**：消费 `GET /api/threads/dashboard` 的 queue 行，显示最新 run 的 attention/
  degraded 状态徽标（用 `text-warning`/`text-destructive` + 文字标签，不仅靠颜色）。
  每行：标题（自动生成，来自 title processor）+ 最新活动时间（`Intl` 按 locale+timeZone）+
  status chip。
- **二级导航**：Skills / Approvals（带待办计数 badge）/ Memory。
- **折叠态**：移动端默认收起为图标条；桌面可手动折叠，状态存浏览器存储（非敏感偏好，合规）。

### 2.2 中间对话区 — 智能区（lobe-ui）

这是唯一允许 lobe-ui 介入的区域。映射后端 `AgentStreamEvent` 到聊天视图。

**布局**（lobe-ui 组件）：

- `ChatHeader`：当前会话标题（`EditableText` 可改名 → `PATCH /api/threads/{id}`）+ 运行状态
  （running/waiting_approval/waiting_input/completed…，带文字标签 + Cyan 等待/运行色）。
- `ChatList` + `ChatItem` + `Bubble`：把 `message.created` / `message.delta` /
  `message.completed` 聚合为气泡。user 气泡 vs assistant 气泡区分对齐与配色。
- `Markdown`（lobe-ui）：渲染 assistant 文本（含 `Mermaid`、`Highlighter` 代码高亮）。
- 思考块：`model.started`→`model.completed` 期间用 lobe-ui 的折叠思考组件展示推理（可选，受
  harness_options 暴露 thinking 决定）。
- **工具调用卡**：`tool.proposed`/`tool.started`/`tool.completed`/`tool.failed`/`tool.denied`
  → 可折叠卡片，展示 tool name、入参摘要（敏感参数 redaction 后）、结果摘要、risk level
  徽标、审批状态。用 `text-warning` 标 on_risk、`text-destructive` 标 denied/failed。
- **运行内嵌横幅**：
  - `input.request` → 在对话底部插入「Agent 需要补充信息」卡片 + 输入框 → `POST /api/runs/{id}/input`。
  - `approval.requested` / `external_approval.requested` → 审批卡，批准/拒绝按钮 →
    `POST /api/approvals/{id}/resolve` 或 `/api/runs/{id}/external-approval/resolve`。
  - `subagent.*` → 子任务委托卡，链接到子 run。
- `ChatInputArea` / `MessageInput`：消息输入 + 发送（`POST /api/runs` 或对 active run
  `POST /api/runs/{id}/input`）。下方一行工具条：技能选择（`Select`）、模型 profile
  （`Select`，仅展示有 scope 的）、附件上传（→ `POST /api/workspaces/{id}/uploads`）。
- `BackBottom` / `AutoScroll`：流式时自动滚到底，但用户上滚后显示「回到底部」按钮。
- `TokenTag` / `LoadingDots`：token 用量提示（来自 `model.usage`）、等待态。
- `DraggablePanel`：可选，让检查面板可拖拽调宽。

**流式接入**：`GET /api/runs/{id}/stream`（SSE）。TanStack Query 不直接管 SSE；用一个
`useRunStream` hook 把 SSE 事件 reducer 成 ChatList 数据 + 推送运行状态。`run.completed`/
`run.failed`/`run.cancelled` 关闭流；`waiting_*` 保持流以接收 resume 后续事件。
`POST /api/runs/stream`（或 thread 版 `/api/threads/{id}/runs/stream`）用于一次性创建并流式跟随。

### 2.3 右侧检查面板 — Inspection（shadcn/ui + TanStack Table，可拖拽 + 默认收起）

按 D2：面板用 lobe-ui `DraggablePanel` 承载，**默认收起为右侧窄条**，只显示当前 run 状态 +
Todo 进度环/条 + attention 徽标。点展开后才显示完整 `Tabs`。窄条态占用最小宽度，让对话区
最大化；长任务运行中或出现 `waiting_*` / `needs_attention` 时可自动高亮提示展开。

展开后 `Tabs` 切换（只读、审计导向）：

- **运行 (Run)**：
  - Todo 列表（`todo.*` 事件 → 进度清单，pending/running/done/blocked 状态徽标）。
  - Trace 时间线：`GET /api/runs/{id}/trace`（`AgentTraceSpan[]`），按 span kind 分组
    （model/tool/sandbox/workspace/artifact/run）。失败 span 用 `text-destructive` + 图标。
  - 事件流原始回放：`GET /api/runs/{id}/events`（折叠进 Drawer，debug 用）。
  - Run tree：`GET /api/runs/{id}/tree`（父子 run / 子代理委托树）。
  - Usage/预算：`GET /api/runs/{id}/usage`、`/tree/usage`，TokenTag 风格条形。
  - Capability audit：`GET /api/runs/{id}/capability-audit`（authorization_decision/audit）。
  - 研究投影（若 deep-research）：execution/evidence ledger/review/continuation/lineage。
  - Operator action hints：sandbox 诊断的 follow-up → `POST .../operator-actions/follow-up`。
- **工作区 (Workspace)**：文件树 + 版本历史 + diff。`GET /api/workspaces/{id}/files`、
  `/files/{path}/versions`、`/diff`、`/snapshot`、`/restore`。图片文件 → `/images/{path}/view`。
  promote 制品 → `/files/{path}/promote`。上传 → `/uploads`，转换 → `/files/{path}/convert`。
- **制品 (Artifacts)**：`GET /api/artifacts`（按 run/workspace 过滤），detail、download metadata、
  content preview（managed file response，非裸主机 FS）。
- **审批 (Approvals)**：该 run 相关 pending 审批，复用 `/api/approvals`。
- **记忆 (Memory)**：`GET /api/runs/{id}/memory-recall`（不暴露完整 context packet 或无限制搜索）。

面板遵循 Admin/Ops 形态（`03` 第 110–122 行）：loading/empty/error/permission-denied/degraded
全状态；破坏性/安全敏感操作需显式确认；绝不展示 secret/token。

## 3. 状态与数据层

- **API 模块**：`src/lib/api/` 下按 feature 分（threads/runs/workspaces/artifacts/approvals/
  memory/skills/modelProfiles/externalTools），typed client，禁止页面内拼 URL（`03` 第 341–349）。
- **TanStack Query**：REST 状态。query key 按 `[feature, id, filters]`；快照/trace 等大对象
  按需懒加载（切到检查面板对应 tab 才请求）。
- **SSE 状态**：`useRunStream(runId)` hook，独立于 Query cache；reducer 把事件投影成
  messages[] / toolCalls[] / todos[] / runStatus / inlineRequests。流结束保留最终态供离线回看。
- **恢复/边界态**：auth 过期、hosted token 交换失败、权限拒绝、离线 → 走 Recovery/Boundary Mode
  （`03` 第 124–134）：展示 app key/org/integration mode/origin + 恢复动作，secret redacted，
  优先 actionable 面板而非 toast。
- **共享组件**：`StatusBadge`（文字+图标+语义色）、`EmptyState`、`ErrorState`、
  `PermissionDenied`、`ConfirmDialog`、`RedactedValue`、`DataTable`（TanStack Table）。

## 4. i18n 与主题桥接

- 子系统自带 i18next 实例 + `I18nextProvider`，namespace：`common`/`errors`/`chat`/
  `inspection`/`skills`/`approvals`/`memory`/`settings`。locale 以
  `runtimeContext.locale.language` 为准（en-US/zh-CN，fallback en-US），响应
  `AITHRU_HOST_CONTEXT_CHANGED.locale`。生产不持久化独立语言偏好。
- 主题：渲染依据 `runtimeContext.theme.resolved`（light/dark），响应
  `AITHRU_HOST_CONTEXT_CHANGED.theme`，不持久化独立主题。语义 token 同时喂给 shadcn 和
  lobe-ui 的 Antd `ConfigProvider`（把 Indigo/Cyan/状态色映射为 Antd theme token），保证视觉
  一致，避免「混主题」。
- API 错误按稳定 `AITHRU_*` code 在 `errors` namespace 本地化；日期/数字走 `Intl` +
  resolved locale + runtime timeZone。

## 5. 仓库与集成边界

- 前端放在 `aithru-agent` 仓库的 `frontend/`（与 `backend/` 同级），独立 Vite 工程，构建产物
  供 Platform 作为 hosted app 挂载。
- 与后端通过 typed HTTP client + SSE 通信（`02` 第 108 行：浏览器前端必须经 typed client /
  postMessage / IPC / HTTP API 与后端通信）。
- 通过 Platform hosted-app SDK 拿 `runtimeContext` + hosted token（仅显式请求所需 scope）。
- 不引入 Flowe 内部、不把 Agent plan 当 workflow graph 编辑（AGENTS.md Hard Boundaries）。

## 6. 决策结论（已落定）

- **D1 组件边界 = 受限混用**：lobe-ui 仅智能区，其余 shadcn/ui+Radix，Antd `ConfigProvider`
  桥接语义 token。
- **D2 检查面板 = 可拖拽分栏 + 默认收起**：`DraggablePanel` 承载，窄条态只显运行状态/Todo
  进度，展开后完整 Tabs。
- **D3 MVP = 全量含管理页**：首期含对话核心、运行检查、Skills、Memory、Approvals、Model
  Profile / External Tool 设置页。
- **D4 列表与聚焦 = 同页侧栏切换**：左栏常驻会话列表，点选同页切换到该会话。

## 7. 下一步建议实现顺序（全量 MVP 内的排期）

1. 工程骨架：`frontend/` Vite6 + React19 + TS + Tailwind3 + shadcn + 路由 + host bridge
   (`AITHRU_HOST_INIT` / `AITHRU_HOST_CONTEXT_CHANGED`) + Antd ConfigProvider token 桥接。
2. `lib/api/` typed client 全 feature 模块 + TanStack Query 接入 + 共享状态组件
   (StatusBadge/Empty/Error/PermissionDenied/ConfirmDialog/RedactedValue/DataTable)。
3. 会话页：左栏 dashboard 列表 + 新建会话 + `EditableText` 改名。
4. 对话智能区：`useRunStream` SSE reducer + ChatList/Bubble/Markdown/工具卡/审批卡/输入请求卡
   + ChatInputArea（技能/profile 选择、附件上传）。
5. 检查面板窄条 + 展开 Tabs：Todo/Trace/RunTree/Usage/Audit/研究投影 → 工作区 → 制品 → 审批
   → 记忆。
6. 管理页：Skills / Approvals / Memory(含候选审批) / Model Profiles / External Tools。
7. Recovery/Boundary 态 + i18n(en-US/zh-CN) + 主题热切换验证。
