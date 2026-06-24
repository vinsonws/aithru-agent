# Clarification Tool Design

**Date**: 2026-06-24
**Status**: draft

## Problem

The current `ClarificationPreflightProcessor` uses word-count rules (default: 4 words) to
block runs with short goals. This is:

- **Too aggressive** — "你好", "帮我" are intercepted even when the model could handle them.
- **Rigid output** — always shows the same prompt: "What should the agent focus on, and what
  result should it produce?"
- **No options** — only free-text input, no clickable choices.
- **Rule-based, not model-driven** — the model never gets a chance to decide whether
  clarification is needed.

## Solution

Replace the word-count preflight with a model-driven `ask_clarification` tool, following
DeerFlow's `ClarificationMiddleware` pattern adapted to Aithru's Pydantic AI architecture.

The model itself decides when clarification is needed, calls `ask_clarification` with
structured parameters, and the system converts the tool call into an `input.requested`
event with rich options.

## Architecture

```
User: "帮我写报告"
  ↓
Pydantic AI model run
  ↓
model calls ask_clarification(
    question="需要什么主题的报告？",
    clarification_type="missing_info",
    options=["技术方案", "市场分析", "产品规划"]
)
  ↓
Pydantic AI returns DeferredToolRequests (tool marked as requires_approval/external)
  ↓
agent/runtime._handle_clarification_request()
  → extract question, clarification_type, options from tool args
  → write input.requested event with structured payload
  → pause run as waiting_input
  ↓
Frontend renders:
  - options present → clickable choice buttons
  - options absent → text prompt + input box
  ↓
User clicks "技术方案" or types reply
  ↓
worker/runner continue_run → build DeferredToolResults
  → resume agent with user input as tool result
  ↓
Model receives clarification answer, continues task
```

## Tool Definition

```python
# ClarificationLocalTool tool signature
def ask_clarification(
    question: str,                                    # The clarification question
    clarification_type: Literal[                      # Category of clarification
        "missing_info",
        "ambiguous_requirement",
        "approach_choice",
        "risk_confirmation",
        "suggestion",
    ] = "missing_info",
    context: str | None = None,                       # Optional background explanation
    options: list[str] | None = None,                 # Optional multiple-choice options
) -> str:
    """Ask the user for clarification before proceeding.
    
    Use this when the request is ambiguous, incomplete, or you need to confirm
    an approach before taking action. The user will see the question and can
    respond directly or choose from provided options.
    """
```

## Event Flow

### 1. Clarification Requested

Worker detects `DeferredToolRequests` containing `ask_clarification`, writes:

```json
{
  "type": "input.requested",
  "source": {"kind": "harness"},
  "payload": {
    "input_request_id": "clarify_{run_id}_{tool_call_id}",
    "tool_call_id": "call_xxx",
    "prompt": "需要什么主题的报告？",
    "reason": "The agent needs more details to proceed",
    "clarification_type": "missing_info",
    "context": "用户请求写报告但未指定主题",
    "options": ["技术方案", "市场分析", "产品规划"]
  }
}
```

Then pauses the run:

```json
{
  "type": "run.paused",
  "source": {"kind": "harness"},
  "payload": {
    "status": "waiting_input",
    "pause_reason": "clarification_requested"
  }
}
```

### 2. User Responds

User clicks option "技术方案" or types text. Backend receives `input.received`:

```json
{
  "type": "input.received",
  "source": {"kind": "user"},
  "payload": {
    "input_request_id": "clarify_{run_id}_{tool_call_id}",
    "value": "技术方案"
  }
}
```

Worker builds `DeferredToolResults` with the user's response as the tool result, then
resumes the agent run.

### 3. Run Resumes

Agent run continues with the clarification answer. The model receives the tool result
and proceeds with the task.

## File Changes

### Backend

| File | Change | Notes |
|------|--------|-------|
| **NEW** `capabilities/local_tools/clarification.py` | `ClarificationLocalTool` defining `ask_clarification` | Register as capability adapter |
| `application/runtime.py` | Add `ClarificationLocalTool` to `tool_adapters` list | |
| `agent/runtime.py` | Extend `_pause_for_deferred_approval` to detect `ask_clarification`, write `input.requested`, pause as `waiting_input`; add `_resume_clarification` for resume flow | Also handles `DeferredToolResults` reconstruction |
| `agent/instructions.py` | Add clarification guidance to system prompt | Teach model when/how to call `ask_clarification` |
| `runtime/processors/clarification.py` | Simplify: remove word-count check, only guard empty/blankspace goals | Keep minimal guard |
| `settings.py` | Remove `clarification_min_goal_words` setting | No longer needed |
| `agent/exceptions.py` | No new exceptions needed (reuses `RunPausedForInput`) | |

### Frontend

| File | Change | Notes |
|------|--------|-------|
| `features/chat/runActivity.ts` | Update `buildRunActivity` to expose `options` from `input.requested` events | |
| `features/inspection/tabs/ActivityTab.tsx` | Render clickable option buttons when `options` present | New component or conditional rendering |
| `features/chat/ChatComposer.tsx` | If user clicked an option, pre-fill the composer | UX enhancement |

## System Prompt Guidance

The system prompt will instruct the model about `ask_clarification`:

```
## When to Ask for Clarification

You have access to the `ask_clarification` tool. Use it when:
- The user's goal is too vague to proceed safely (e.g. "do something")
- You need to choose between approaches (provide `options`)
- The requested action has important implications that need confirmation

Do NOT use it:
- When the goal is clear enough to proceed
- For simple informational questions
- When you already have enough context from the workspace or memory

When providing options, keep them concise (2-5 choices). When there are no clear
options, just ask a focused question without options.
```

## Migration

1. `ClarificationPreflightProcessor` no longer pauses runs for word-count reasons.
   Only triggers for truly empty goals.
2. Remove `clarification_min_goal_words` setting (backward-compat: ignore if set).
3. Existing runs with `waiting_input` status from old preflight continue to work.

## Testing

- Unit: `ClarificationLocalTool` descriptor produces correct schema
- Unit: `_handle_clarification_request` extracts args and writes correct events
- Integration: model calls `ask_clarification` → `input.requested` event emitted → run paused
- Integration: user responds → `DeferredToolResults` built → run resumes → model continues
- E2E: "帮我写报告" → model asks clarification → user picks option → agent completes task
