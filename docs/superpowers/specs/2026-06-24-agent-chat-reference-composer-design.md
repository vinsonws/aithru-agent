# Agent Chat Reference Composer Design

Date: 2026-06-24

## Goal

Redesign the chat composer so it feels like a calm, natural agent input surface
similar to the approved reference: a large rounded input container with quiet
tool controls along the bottom edge.

This is a frontend-only refinement. It keeps Aithru Agent as an AI harness and
does not introduce workflow graph editing, Agent-owned workflow semantics,
workflow scheduling, or persisted AgentPlan-as-workflow behavior.

## Approved Direction

Use the **Reference Composer** direction approved in the visual companion.

The composer should have:

- a wide white input shell;
- large rounded corners;
- a subtle border and soft shadow;
- one spacious multiline input area;
- low-noise bottom controls split left and right;
- a circular send button on the far right.

The reference intent is calm and tactile rather than console-like. The input
itself is the dominant element.

## Default Surface

The default composer surface contains:

- multiline text input;
- attachment button;
- execution permission selector on the left;
- combined model and reasoning selector on the right;
- circular send button;
- stop button in the send position while a run is active.

There is no default skill selector and no `@` context button in this composer.
Detailed permission, reasoning, and model controls open in compact popovers
above the input surface instead of expanding below it.

## Initial Thread State

The new-thread screen uses the same composer surface as the in-thread composer.
The greeting text and composer are centered in the main content area, and prompt
templates render as small stamp-like pills below the composer instead of cards
above it.

## Visual Rules

- The composer sits in the existing bottom chat area.
- The outer wrapper should look like a single input object, not a stack of
  cards.
- Use a white surface on light theme and the existing card/dark surface on dark
  theme.
- Keep border and shadow subtle enough that the composer feels integrated with
  the chat.
- Use stable dimensions so hover, slash command hints, disabled states, and
  running states do not resize the surrounding layout.
- Avoid nested cards, decorative gradients, badges, and heavy toolbar rows.

## Interaction Rules

- `Enter` sends and `Shift+Enter` inserts a newline.
- Empty input disables send.
- Pending run creation disables send.
- Active runs show stop/cancel in the primary action position.
- Slash command suggestions remain available when the input starts with `/`, and
  they render above the composer.
- Prompt template chips appear below the composer when the input is empty and no
  run is active.
- Clicking the permission area opens the permission popover above the composer.
- Clicking the model/reasoning area opens the combined reasoning and model
  popover above the composer.
- Reasoning levels map to existing harness modes and do not introduce new
  backend workflow or scheduling semantics.

## Responsive Rules

- On desktop, bottom controls stay in one row with left tools and right status.
- On narrow screens, controls may wrap into two compact rows.
- The model label truncates before controls overflow.
- The circular primary action remains visible and reachable.
- The composer must not cause horizontal scrolling.

## Implementation Scope

Primary code changes should stay in:

- `frontend/src/features/chat/ChatComposer.tsx`;
- `frontend/src/features/conversation/NewThreadPage.tsx` when the empty/new
  thread input uses its own composer surface;
- related i18n resources if visible copy changes;
- focused tests for composer rendering or existing composer state helpers.

Do not change backend APIs or capability boundaries for this design.

## Verification

Verify:

- desktop composer visual shape matches the approved reference direction;
- narrow viewport has no horizontal overflow;
- send, disabled send, stop/cancel, slash hint, template click, and settings
  expansion still work;
- existing frontend tests for composer and chat still pass.
