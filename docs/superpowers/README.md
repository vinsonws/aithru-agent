# Superpowers Planning Notes

Status: historical planning archive plus current replacement spec

Files in `docs/superpowers/plans/` and older dated specs are implementation
notes from earlier backend phases. Many of them reference the removed Python
backend and are preserved only as history.

Current backend work must use the native TypeScript direction:

- `docs/00-agent-harness-design.md`
- `docs/ARCHITECTURE.md`
- `docs/superpowers/specs/2026-06-29-native-ts-agent-backend-replacement-design.md`

Do not implement new backend work from older Python/Pydantic plans. If an older
idea is still useful, port the product intent into `backend/` using Aithru
contracts, the native model turn loop, and the capability router.
