# Agent Presentation Model Design

Status: approved design

Supersedes:

- `docs/superpowers/specs/2026-06-25-conversation-display-cards-design.md`

## Goal

Replace Display Cards with a first-class Presentation model that lets the
Agent Harness express what has been presented to the user, how the user should
view it, and which lightweight UI effects are allowed.

This is a breaking semantic reset. There is no compatibility layer for
`AgentDisplayCard`, `display.card.created`, or `display_cards`.

The product rule is:

```txt
Models may request presentations.
The harness validates resources, views, effects, and actions.
The frontend renders and executes only trusted presentation events.
The model sees a ledger of backend-confirmed presentations, not arbitrary DOM state.
```

## Problem

`DisplayCard` names a frontend shape rather than a product concept. As soon as
the system needs to open side panels, choose between HTML/source/text views,
focus an approval, highlight a retry action, or tell the model what is already
visible to the user, "card" becomes the wrong abstraction.

The current design also collapses separate concerns:

- the resource being presented;
- the view mode used for that resource;
- the surface where it appears;
- the frontend effect requested by the harness;
- the user actions available from that presentation.

That makes the protocol hard to extend beyond file and artifact cards.

## Non-Goals

- Do not let the model send arbitrary UI schemas, component names, CSS, JSX,
  HTML wrappers, frontend route names, or browser scripts.
- Do not let the frontend infer product presentations from raw tool names.
- Do not preserve `AgentDisplayCard`, `display.card.*`, or `display_cards`.
- Do not turn UI effects into a general remote-control channel for the
  browser.
- Do not make presentations workflow definitions, graph nodes, checkpoints, or
  scheduler inputs.

## Core Concepts

### Resource

A resource is the harness-controlled thing being presented.

Initial resource kinds:

```txt
artifact
workspace_file
approval
todo
run
trace_span
external_url
none
```

Rules:

- `artifact` requires an artifact id.
- `workspace_file` requires a workspace path.
- `approval`, `todo`, `run`, and `trace_span` require scoped ids.
- `external_url` requires a backend-approved URL.
- `none` is allowed only for pure status presentations.

### Presentation

A presentation is the backend-confirmed fact that a resource or state should be
shown to the user.

It is not a card. The frontend may render it as a row, card-like item, side
panel preview, header attention hint, approval panel entry, or activity item.

### View

A view is how the resource can be inspected.

Initial view kinds:

```txt
html_preview
source_text
markdown
json
image
pdf
diff
approval_review
activity_detail
download
open_external
none
```

Rules:

- `preferred_view` is the default view selected by the harness.
- `available_views` is the complete backend-approved view set.
- The model may request a preferred view, but the backend may replace it.
- The frontend must not invent privileged views that are absent from
  `available_views`.

### Surface

A surface is where the presentation is eligible to appear.

Initial surface kinds:

```txt
conversation
side_panel
approval_panel
activity
header
```

Multiple surfaces are allowed. For example, a generated HTML artifact can have
`conversation` and `side_panel`; an approval can have `conversation`,
`approval_panel`, and `header`.

### Effect

An effect is a lightweight frontend behavior requested by the trusted
presentation event.

Initial effect kinds:

```txt
open_panel
focus_presentation
scroll_to
highlight
none
```

Effects are advisory and bounded:

- The frontend may ignore an effect if the current viewport or product state
  makes it inappropriate.
- Effects must reference a known presentation, surface, or panel enum.
- Effects must not include component names, CSS selectors, scripts, arbitrary
  URLs, or freeform DOM instructions.

### Action

An action is a user-triggered operation exposed with the presentation.

Initial action kinds:

```txt
open_view
download
approve
reject
retry
continue
open_in_workbench
open_external
copy_reference
none
```

Actions are not automatically executed by the model. They are presented to the
user and, when clicked, call existing controlled APIs.

## Domain Contract

Add the following domain models and remove the Display Card models.

```txt
AgentPresentation
  id
  org_id
  thread_id
  run_id
  sequence?
  status
  priority
  title
  summary?
  reason?
  resource
  surfaces[]
  preferred_view
  available_views[]
  effects[]
  actions[]
  source
  metadata?
  created_at?
  updated_at?
```

Supporting models:

```txt
AgentPresentationResource
  kind
  id?
  path?
  url?

AgentPresentationEffect
  kind
  panel?
  surface?
  presentation_id?
  mode?

AgentPresentationAction
  kind
  label
  view?
  path?
  method?
  requires_confirmation?

AgentPresentationSource
  created_by: harness | tool | model_request
  event_id?
  tool_call_id?
  tool_name?
```

Recommended literal values:

```txt
status: pending | ready | failed | dismissed
priority: low | normal | high
effect.mode: soft | assertive
```

`soft` effects are polite suggestions such as opening the side panel when no
user interaction is in progress. `assertive` effects are for attention states
such as approval required, but still remain bounded frontend behavior.

## Stream Events

Remove:

```txt
display.card.created
display.card.updated
```

Add:

```txt
presentation.created
presentation.updated
```

`presentation.created` inserts or replaces a presentation by id.
`presentation.updated` updates status, views, actions, effects, title,
summary, or reason while preserving canonical stream order.

Event payload:

```json
{
  "presentation": {
    "id": "presentation_123",
    "thread_id": "thread_1",
    "run_id": "run_1",
    "status": "ready",
    "priority": "normal",
    "title": "index.html",
    "reason": "Show the generated webpage as an interactive preview.",
    "resource": {"kind": "artifact", "id": "artifact_3"},
    "surfaces": ["conversation", "side_panel"],
    "preferred_view": "html_preview",
    "available_views": ["html_preview", "source_text", "download"],
    "effects": [
      {"kind": "open_panel", "panel": "preview", "mode": "soft"}
    ],
    "actions": [
      {"kind": "open_view", "label": "Preview", "view": "html_preview"},
      {"kind": "open_view", "label": "Source", "view": "source_text"},
      {"kind": "download", "label": "Download"}
    ],
    "source": {
      "created_by": "model_request",
      "tool_call_id": "call_123",
      "tool_name": "presentation.present"
    }
  }
}
```

## Presentation Tool

Replace or rewrite `present_resources` as:

```txt
presentation.present
```

Input:

```json
{
  "resources": [
    {"kind": "artifact", "id": "artifact_3"}
  ],
  "surfaces": ["conversation", "side_panel"],
  "preferred_view": "html_preview",
  "effects": [
    {"kind": "open_panel", "panel": "preview", "mode": "soft"}
  ],
  "reason": "Show the generated webpage as an interactive preview."
}
```

The tool input intentionally omits titles, arbitrary component names, styling,
and raw frontend schemas. The model requests presentation intent; the harness
creates trusted presentation facts.

The capability router must:

- validate that each resource exists and belongs to the current org, thread,
  run, workspace, or approved external scope;
- validate required scopes and allowed tools;
- derive safe `available_views` from resource type, MIME type, file extension,
  artifact metadata, and policy;
- select or replace `preferred_view`;
- validate requested surfaces and effects;
- derive safe actions;
- redact sensitive metadata;
- emit `presentation.created`;
- return accepted and rejected presentation requests to the model.

Tool result:

```json
{
  "presentations": [
    {
      "id": "presentation_123",
      "resource": {"kind": "artifact", "id": "artifact_3"},
      "status": "ready",
      "preferred_view": "html_preview",
      "available_views": ["html_preview", "source_text", "download"],
      "surfaces": ["conversation", "side_panel"]
    }
  ],
  "rejected_requests": []
}
```

## Automatic Projection

The harness may create presentations without a model request.

Initial projections:

- `artifact.create` can create a pending or ready artifact presentation.
- `artifact.finalize` can update an artifact presentation to ready.
- `workspace.write_file` and `workspace.patch_file` can create workspace file
  presentations.
- `sandbox.write_file`, `sandbox.patch_file`, and `sandbox.promote_file` can
  create workspace or artifact presentations.
- approval requests can create approval review presentations.
- failed runs or sandbox errors can create activity presentations with retry
  actions.

Automatic projections use `source.created_by = "harness"` or `"tool"`.
Model-requested presentations use `source.created_by = "model_request"`.

## View Resolution

The backend owns view resolution. The frontend renders only approved views.

For artifacts and workspace files:

- `text/html`, `.html`, and `.htm` may resolve to `html_preview` and
  `source_text`.
- `text/markdown`, `.md`, and `.markdown` may resolve to `markdown` and
  `source_text`.
- `application/json` and `.json` may resolve to `json` and `source_text`.
- supported image media types may resolve to `image` and `download`.
- `application/pdf` and `.pdf` may resolve to `pdf` and `download`.
- text-like files may resolve to `source_text`.
- unsupported binaries resolve to `download`.

If media type is missing, the backend should infer from `artifact.name`,
`artifact.uri`, or workspace path before falling back to `source_text`.

HTML preview must be sandboxed. A safe frontend implementation may fetch the
content as text, inject a base element when needed, create a `Blob` with
`text/html;charset=utf-8`, and render that blob in a sandboxed iframe. Directly
iframes to backend artifact URLs are allowed only when the backend response is
explicitly safe for active content.

## Frontend Behavior

Replace Display Card components with Presentation components.

Recommended frontend names:

```txt
PresentationItem
PresentationTile
PresentationPreview
PresentationActions
presentationTimeline
```

The chat timeline should include:

```txt
ChatTimelineItem
  kind: presentation
  presentation: PresentationEntry
```

The renderer should:

- show conversation-surface presentations inline in stream order;
- open or update side panel state only from approved effects;
- support view switching across `available_views`;
- never execute unknown effects;
- never render unknown actions as live controls;
- degrade unknown resource or view kinds to a safe text/download presentation.

Unknown enum values should not crash the app. They should render a safe generic
presentation with no privileged actions.

## Model Visibility

The model should know what the harness has confirmed as presented, but should
not know or depend on arbitrary client DOM state.

Prompt assembly should include a compact presentation ledger:

```txt
Presented to user:
- presentation_123
  resource: artifact artifact_3
  title: index.html
  status: ready
  surfaces: conversation, side_panel
  preferred view: html_preview
  available views: html_preview, source_text, download
```

The `presentation.present` tool result should also return the accepted
presentations. The model can then truthfully say things like:

```txt
I opened the generated webpage preview in the side panel. You can also switch
to source text or download it.
```

If client acknowledgement is needed later, add a separate optional event such
as `presentation.client_acknowledged`. It is out of scope for the first
implementation.

## API And Snapshot Changes

Remove:

```txt
display_cards
```

Add:

```txt
presentations
```

Affected projections include:

- run snapshot;
- thread workbench;
- event snapshot routes;
- generated OpenAPI types;
- frontend API types.

The presentation list is derived from canonical stream events. It is a
read-only projection over harness facts.

## Deletion Scope

Delete or replace:

- `AgentDisplayCard*` domain models;
- `stream/display_cards.py`;
- display card imports from stream, routes, snapshots, and tool bridge;
- `display.card.created` and `display.card.updated` event handling;
- `display_cards` API fields;
- `DisplayCard.tsx`;
- `DisplayCardEntry`;
- chat timeline `kind: "card"`;
- display card frontend and backend tests;
- display card documentation references.

Add:

- `AgentPresentation*` domain models;
- `stream/presentations.py`;
- `presentation.created` and `presentation.updated` event handling;
- `presentations` API fields;
- `presentation.present` local tool;
- automatic presentation projections for user-facing resources;
- presentation prompt ledger;
- frontend presentation timeline items and renderer tests.

## Security And Policy

Presentations must preserve the existing capability boundary:

```txt
model request
  -> presentation.present tool
  -> Aithru Capability Router
  -> policy / scope / approval boundary
  -> resource validation and view resolution
  -> presentation event
  -> frontend trusted renderer
```

The model does not execute frontend behavior. The frontend executes only
bounded effects from trusted backend events.

Sensitive metadata must be redacted before it enters presentation payloads,
prompt ledgers, or frontend snapshots.

External URLs require explicit validation and should default to user-clicked
actions rather than automatic navigation.

## Testing

Backend tests:

- domain validation for resources, views, effects, and actions;
- `presentation.present` accepts valid scoped resources;
- invalid resources, forbidden views, and unsupported effects are rejected;
- automatic projections emit `presentation.created` in the correct stream
  order;
- `presentation.updated` preserves identity and updates status/actions/views;
- snapshots expose `presentations` and no longer expose `display_cards`;
- prompt context includes the compact presentation ledger.

Frontend tests:

- stream reducer handles `presentation.created` and `presentation.updated`;
- timeline interleaves presentations with reasoning, tools, and assistant text;
- presentation renderer only shows approved actions;
- side panel opens only for approved `open_panel` effects;
- HTML artifacts can render as sandboxed preview and source text;
- unknown views/effects/actions degrade safely.

End-to-end checks:

- an HTML artifact with missing media type but `.html` name presents as
  `html_preview` plus `source_text`;
- a generated Markdown report presents as `markdown`;
- an approval request opens the approval review surface assertively;
- a failed run presents retry guidance without exposing arbitrary UI commands.

## Implementation Notes

Because compatibility is intentionally out of scope, implementation should make
test failures obvious by removing old names rather than aliasing them.

Recommended order:

1. Add domain models and stream projection tests for presentations.
2. Replace backend display card projection with presentation projection.
3. Replace `present_resources` with `presentation.present`.
4. Update snapshots, workbench, and OpenAPI types.
5. Replace frontend stream state and timeline card handling.
6. Add presentation renderer and side panel effects.
7. Add prompt presentation ledger.
8. Delete old display card files and tests.
