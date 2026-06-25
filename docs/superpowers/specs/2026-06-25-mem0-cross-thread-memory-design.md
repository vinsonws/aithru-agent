# Mem0 Cross-Thread Memory Design

**Date**: 2026-06-25
**Status**: draft

## Problem

The current Agent memory layer is shaped around scoped key/value entries and
pending memory candidates. It is useful for explicit, auditable local memory,
but it does not provide natural cross-thread long-term memory:

- Completed runs create pending candidates, so future runs do not recall them
  until an operator approves each candidate.
- Candidate values are derived from final run output, not from semantic
  conversation memory.
- The model does not benefit from user preferences and stable project facts
  across threads unless they were manually stored or approved.
- The shape differs from DeerFlow-style memory, where conversations update
  long-term memory automatically and later runs receive formatted memory
  context.

The target is a more native Mem0 integration: automatic long-term memory across
threads, with Aithru preserving identity boundaries, redaction, traceability,
and user control without requiring approval for every memory write.

## Decision

Use Mem0 as the primary long-term memory engine for cross-thread memory.
Aithru remains the harness boundary that decides when to search, when to add,
how identities map to tenants/users/agents, what metadata and filters are
applied, and which events are recorded.

Existing Aithru memory entries remain useful as local pinned or legacy memory,
but they are not the canonical cross-thread long-term memory representation in
Mem0 mode.

## Non-Goals

- Do not expose unrestricted Mem0 tools directly to model code.
- Do not make Agent memory into an Aithru Core `WorkflowSpec`, scheduler, graph,
  or plan definition.
- Do not require per-memory approval in the default Mem0-native path.
- Do not store secrets, credentials, service tokens, raw sensitive tool
  payloads, or unrestricted workspace contents in Mem0.
- Do not replace thread summaries, todos, artifacts, or trace events with
  memory. They remain separate harness state.

## Architecture

```txt
Run start / user turn
  -> build a memory query from the task, recent messages, and thread summary
  -> Mem0 search with Aithru identity filters
  -> convert results into bounded AgentMemoryRecallItem context
  -> inject through AgentRunContextPacket

Run completed / compacted
  -> collect bounded user and assistant turns
  -> redact and apply no-memory filters
  -> Mem0 add(messages, user_id, app_id, agent_id, run_id, metadata)
  -> emit memory lifecycle events
```

Aithru owns the lifecycle. Mem0 owns semantic extraction, update, search, and
ranking.

## Identity Mapping

Mem0 entity ids must prevent cross-tenant leakage while still enabling
cross-thread recall.

```txt
Mem0 user_id  = "{org_id}:{actor_user_id}"
Mem0 app_id   = "{deployment_id}:aithru-agent" or "{org_id}:aithru-agent"
Mem0 agent_id = skill_id when a skill-specific memory profile is useful,
                otherwise "aithru-agent"
Mem0 run_id   = Aithru run_id for write provenance
metadata      = org_id, actor_user_id, thread_id, workspace_id, project_id,
                skill_id, run_id, source, retention, created_by
```

Search filters must include the tenant/user boundary. Thread and workspace ids
are metadata for relevance and debugging, not the default primary boundary for
cross-thread recall.

## Read Path

At context-packet build time:

1. If the run lacks `agent.memory.read` or `*`, skip Mem0 search.
2. Build a concise query from the current task, latest user message, recent
   thread summary, and optional skill name.
3. Search Mem0 using the mapped entity ids and filters.
4. Drop results that fail Aithru visibility, retention, or forbidden-content
   checks.
5. Convert retained results into `AgentMemoryRecallItem` with
   `source="mem0"`.
6. Merge with local pinned memory, dedupe, and enforce context budget limits.
7. Emit a `memory.search.completed` event with counts and timing, without raw
   sensitive payloads.

Mem0 results are context hints, not authority. Instructions should continue to
tell the model to prefer current user input and repo files over stale memory.

## Write Path

At run completion or thread compaction:

1. If the run lacks `agent.memory.write` or `*`, skip Mem0 writes.
2. Collect only bounded user and assistant messages needed for memory update.
3. Exclude raw tool outputs, credentials, secrets, approval payloads, and
   configured no-memory content.
4. Redact sensitive strings before sending data to Mem0.
5. Call Mem0 `add` with `infer=True` so Mem0 extracts and updates memories.
6. Store Aithru lifecycle events for search/add success, failure, skipped
   reason, and provider latency.

Default Mem0-native mode does not create `AgentMemoryCandidate` records and
does not require operator approval for normal memory extraction.

## User Control

Approval is replaced by memory governance controls:

- Per-user memory on/off.
- Per-project or per-skill memory on/off.
- A "do not remember this" signal for a run or message.
- Forget APIs that delete by user, memory id, thread metadata, or project
  metadata where the provider supports it.
- Admin visibility into memory events and provider errors without exposing
  raw secrets.
- Configurable forbidden memory categories such as credentials, payment data,
  health data, and other sensitive payloads.

Enterprise deployments may re-enable candidate approval as a policy mode, but
that mode is not the default Mem0-native experience.

## Existing Memory Layer

The existing `AgentMemoryEntry` and `AgentMemoryCandidate` models are retained
with narrower meaning:

- `AgentMemoryEntry`: local pinned memory, explicit rules, migration fallback,
  and provider-independent recall projection.
- `AgentMemoryCandidate`: optional compliance review path, disabled by default
  for Mem0-native long-term memory.
- `AgentMemoryRecallItem`: provider-neutral prompt injection shape used by
  local memory and Mem0 recall.
- `memory.search` and `memory.remember`: explicit local tools, not the primary
  Mem0 lifecycle API.

This avoids forcing Mem0's semantic memory model into a key/value approval
schema while preserving existing APIs for compatibility.

## Settings

Add memory provider settings:

```txt
long_term_memory_provider = "local" | "mem0"
mem0_mode = "platform" | "oss"
mem0_api_key = optional secret
mem0_org_boundary = "org_actor_user"
mem0_app_id = optional deployment/app id
mem0_default_agent_id = "aithru-agent"
mem0_top_k = 8
mem0_threshold = provider default unless configured
mem0_add_on_run_complete = true
mem0_add_on_compaction = true
mem0_approval_required = false
mem0_no_memory_markers = ["do not remember", "don't remember"]
```

Secrets must come from runtime configuration, not from model-visible context.

## Events

Add auditable lifecycle events:

```txt
memory.search.started
memory.search.completed
memory.search.skipped
memory.add.started
memory.add.completed
memory.add.failed
memory.add.skipped
memory.forget.requested
memory.forget.completed
```

Events should include ids, counts, latency, provider name, and skip/failure
reason. They should not include raw secret values or full memory payloads unless
the event visibility policy explicitly permits it.

## API Surface

Keep current local memory APIs for compatibility. Add provider-aware control
plane routes only where product UX needs them:

- inspect recalled memory for a run;
- disable memory for a user/project/skill;
- forget memories by memory id or scoped metadata;
- view provider health and sync failures.

Do not add graph editing, scheduler behavior, or persisted AgentPlan memory
semantics.

## Testing

- Unit: identity mapping creates tenant-safe Mem0 ids.
- Unit: read path skips without `agent.memory.read`.
- Unit: write path skips without `agent.memory.write`.
- Unit: redaction removes configured sensitive values before Mem0 add.
- Unit: no-memory marker prevents add for that run/message.
- Integration: run in thread A writes to Mem0, run in thread B for the same
  user recalls it.
- Integration: different org or actor does not recall the same memory.
- Integration: Mem0 failure emits an event and does not fail the user run.
- Integration: local pinned memory and Mem0 memory merge into a bounded context
  packet.

## Migration

1. Add Mem0 provider behind a disabled-by-default setting.
2. Implement cross-thread read first, with fixture-backed tests.
3. Enable run-complete Mem0 add for configured environments.
4. Keep candidate extraction available for local provider mode.
5. Document Mem0-native mode as the target long-term memory path once the read
   and write lifecycle is verified.

## References

- Mem0 add memory: https://docs.mem0.ai/core-concepts/memory-operations/add
- Mem0 search memory: https://docs.mem0.ai/core-concepts/memory-operations/search
- Mem0 entity-scoped memory: https://docs.mem0.ai/platform/features/entity-scoped-memory
- Mem0 async client: https://docs.mem0.ai/platform/features/async-client
- DeerFlow memory source: https://github.com/bytedance/deer-flow/tree/main/backend/packages/harness/deerflow/agents/memory
