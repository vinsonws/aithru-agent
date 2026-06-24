# Agent Chat Reference Composer Implementation Notes

Date: 2026-06-24

## Implemented Shape

- Added a shared `ReferenceComposerSurface` for the new-thread page and the
  in-thread composer.
- Kept the large rounded input shell, quiet bottom controls, and circular
  primary action.
- Moved execution permission to the left side of the composer toolbar.
- Combined reasoning intensity and model selection in one right-side popover.
- Removed composer skill configuration and the `@` context button.
- Rendered slash-command suggestions above the composer.
- Rendered new-thread prompt templates as small stamp-like pills below the
  composer.

## State Mapping

Reasoning is a frontend presentation layer over the existing harness modes:

- `quick` maps to `chat`;
- `thinking` maps to `auto`;
- `pro` maps to `plan`;
- `ultra` maps to `plan`.

This keeps the redesign frontend-only and does not add new workflow semantics or
backend scheduling behavior.

## Verification

- `npm test`
- `npm run typecheck`
- Browser layout checks for desktop new-thread, mobile new-thread, and in-thread
  composer surfaces.
