# Agent Chat Conversation Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the run chat display read as a quiet conversation flow with aligned assistant thinking, tool calls, and final answers.

**Architecture:** Keep the current SSE reducer, but add reasoning segment support and project the run into ordered chat timeline items. Replace large activity cards in the main chat with a lightweight assistant process disclosure and compact tool rows.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind, node:test.

## Global Constraints

- Do not fake thinking content when the stream does not provide it.
- Do not add avatars to the conversation flow.
- Keep real tool details behind an expandable row.
- Keep completion summary lightweight.
- Preserve existing capability boundary behavior.

---

### Task 1: Timeline Projection

**Files:**
- Modify: `frontend/src/features/chat/useRunStream.ts`
- Modify: `frontend/src/features/chat/chatTimeline.ts`
- Test: `frontend/tests/chat-timeline.test.mjs`

**Interfaces:**
- Consumes: existing `RunStreamState`, `ToolCallEntry`, and `ChatMessage`.
- Produces: reasoning segments and ordered timeline items for `ChatPanel`.

- [ ] Add `ReasoningSegment` to `useRunStream.ts`.
- [ ] Reduce future reasoning event aliases into `state.reasoningSegments`.
- [ ] Update `buildChatTimeline` to include a process item only when model timing, tools, todos, inline requests, or reasoning segments exist.
- [ ] Update timeline tests for `reasoning -> tool -> reasoning -> assistant message`.

### Task 2: Conversation Rendering

**Files:**
- Modify: `frontend/src/features/chat/ChatPanel.tsx`
- Modify: `frontend/src/features/chat/ToolCallCard.tsx`
- Modify: `frontend/src/i18n/resources/en/chat.json`
- Modify: `frontend/src/i18n/resources/zh/chat.json`

**Interfaces:**
- Consumes: timeline items and `RunStreamState`.
- Produces: avatarless user/assistant message layout, assistant process disclosure, compact completion footer.

- [ ] Remove avatar chrome from chat messages.
- [ ] Render user messages as right bubbles.
- [ ] Render assistant messages as left prose without a bordered card.
- [ ] Render process summary as a small disclosure row.
- [ ] Render tool calls as compact inline rows.
- [ ] Render completion as a small footer under the assistant turn.

### Task 3: Verification

**Files:**
- Test: `frontend/tests/chat-timeline.test.mjs`

**Commands:**
- `cd frontend && npm test`
- `cd frontend && npm run typecheck`

- [ ] Run focused tests.
- [ ] Run frontend test suite.
- [ ] Run typecheck.
- [ ] Verify the browser view at the active chat URL.
