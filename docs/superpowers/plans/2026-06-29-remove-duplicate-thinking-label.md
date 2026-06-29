# Remove Duplicate Thinking Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the repeated "Thinking" subheading from assistant process reasoning content while keeping the process summary and reasoning body visible.

**Architecture:** The chat timeline data shape stays unchanged. `ChatPanel.tsx` continues to render reasoning segments inside the assistant process disclosure, but the segment body no longer has a redundant static label above it.

**Tech Stack:** React, TypeScript, Node test runner, source-level frontend regression tests.

## Global Constraints

- Keep real reasoning content visible only when present in the stream.
- Keep tool rows and assistant process ordering unchanged.
- Do not introduce Agent workflow semantics or graph behavior.

---

### Task 1: Remove the Redundant Reasoning Subheading

**Files:**
- Modify: `frontend/tests/chat-conversation-flow.test.mjs`
- Modify: `frontend/src/features/chat/ChatPanel.tsx`

**Interfaces:**
- Consumes: `ChatTimelineItem` assistant process steps with `kind: "reasoning"` and `content: string`.
- Produces: Assistant process UI where the summary line provides the process label and the reasoning body renders directly below it.

- [ ] **Step 1: Write the failing test**

```js
test("assistant process reasoning content omits repeated Thinking subheading", async () => {
  const source = await src("features/chat/ChatPanel.tsx");

  assert.doesNotMatch(source, /chat:process\.thinkingLabel/);
  assert.match(source, /<Markdown variant="chat">\{step\.content\}<\/Markdown>/);
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `cd frontend && npm test -- tests/chat-conversation-flow.test.mjs`

Expected: FAIL because `ChatPanel.tsx` still references `chat:process.thinkingLabel`.

- [ ] **Step 3: Remove the label from the reasoning step markup**

Replace the reasoning step block with:

```tsx
<div key={step.id} className="py-1 text-sm text-muted-foreground">
  {step.content.trim() ? (
    <Markdown variant="chat">{step.content}</Markdown>
  ) : (
    <LoadingDots />
  )}
</div>
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `cd frontend && npm test -- tests/chat-conversation-flow.test.mjs`

Expected: PASS with the new regression check included.

- [ ] **Step 5: Run frontend validation**

Run: `cd frontend && npm test`

Expected: PASS for all frontend source-level tests.
