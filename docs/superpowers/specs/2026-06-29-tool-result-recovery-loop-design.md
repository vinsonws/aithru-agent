# Tool Result Recovery Loop Design

Status: approved design

## Purpose

Aithru Agent needs a controlled self-correction path for model-proposed tool
calls. When the model supplies bad arguments, chooses a missing resource, or
encounters a recoverable provider/tool failure, the harness should be able to
return structured failure information to the model so it can choose corrected
arguments, select a different tool, or produce a degraded result.

This is not a worker-level full-run retry system. Recovery belongs at the tool
result boundary, where the failed action and its policy context are precise.

## Goals

- Let the model correct recoverable tool input and execution failures inside
  the same model run.
- Preserve the Aithru Capability Router as the boundary for every real action.
- Keep policy, scope, approval, redaction, audit, and event ordering explicit.
- Avoid repeating side effects by retrying a whole run after a tool failure.
- Give the UI and trace plane enough facts to explain what failed, what was
  offered back to the model, and when the recovery budget was exhausted.
- Keep runtime todos and plans as harness state, not recovery state machines or
  workflow definitions.

## Non-goals

- Do not make worker retry a general LLM correction loop.
- Do not bypass tool policy, scope checks, approval, or redaction when the model
  retries with corrected input.
- Do not let policy or security denials become model-correctable by default.
- Do not add Agent-owned workflow graph, branch, scheduler, or persisted plan
  semantics.
- Do not require every tool failure to be recoverable.

## Recommended Approach

Use a Tool Result Recovery Loop:

```txt
LLM proposes tool call
  -> Pydantic AI tool wrapper
  -> Aithru Tool Bridge
  -> Aithru Capability Router prepare/execute
  -> concrete tool adapter
  -> AgentToolCallResult

completed:
  -> emit tool.completed
  -> return output to model

failed or denied with recoverable recovery:
  -> emit tool.failed or tool.denied with recovery metadata
  -> emit tool.recovery.offered
  -> return safe recovery payload to model
  -> model may call a tool again through the router

failed or denied without recoverable recovery:
  -> raise AgentError
  -> worker emits model.failed and run.failed
```

The model never executes corrected inputs directly. It only receives guidance.
Any retry is a new model-proposed tool call that crosses the same capability
boundary again.

## Failure Kinds

Tool failures should be classified with stable failure kinds:

```txt
invalid_input        Model supplied malformed or semantically invalid input.
not_found            Requested resource does not exist or cannot be located.
transient            Provider, network, or dependency failed temporarily.
execution_failed     Controlled execution failed but can be adjusted.
ambiguous_input      The model needs more user input before a safe retry.
policy_denied        Scope, skill, tool policy, or security denied the action.
approval_required    The correct path is approval, not model correction.
fatal_system         Harness or adapter invariant failed.
```

Default recoverability:

| Failure kind | Default action |
| --- | --- |
| `invalid_input` | Return to model with guidance. |
| `not_found` | Return to model with list/search guidance when safe. |
| `transient` | Return to model when fallback or degraded completion is safe. |
| `execution_failed` | Return to model for controlled sandbox/tool adjustment. |
| `ambiguous_input` | Pause through input request or return guidance to ask the user. |
| `policy_denied` | Fail or deny; do not ask the model to bypass policy. |
| `approval_required` | Pause for approval. |
| `fatal_system` | Fail the run. |

## Domain Contract

Extend `AgentToolCallResult` with optional recovery metadata.

```python
class AgentToolFailureKind(StrEnum):
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    TRANSIENT = "transient"
    EXECUTION_FAILED = "execution_failed"
    AMBIGUOUS_INPUT = "ambiguous_input"
    POLICY_DENIED = "policy_denied"
    APPROVAL_REQUIRED = "approval_required"
    FATAL_SYSTEM = "fatal_system"


class AgentToolRecoveryAction(StrEnum):
    RETURN_TO_MODEL = "return_to_model"
    RETRY_WITH_CORRECTED_INPUT = "retry_with_corrected_input"
    USE_ALTERNATIVE_TOOL = "use_alternative_tool"
    ASK_USER = "ask_user"
    WAIT_OR_DEGRADE = "wait_or_degrade"
    REQUIRE_APPROVAL = "require_approval"
    FAIL_RUN = "fail_run"


class AgentToolRecovery(AithruBaseModel):
    recoverable: bool
    kind: AgentToolFailureKind
    action: AgentToolRecoveryAction
    message: str
    model_guidance: str | None = None
    suggested_input: object | None = None
    allowed_values: dict[str, object] | None = None
    retry_after_ms: int | None = None
    attempt_key: str | None = None
    max_attempts: int = 2
```

`AgentToolCallResult` gains:

```python
recovery: AgentToolRecovery | None = None
```

The existing descriptor-level `failure_policy` remains an upper-level harness
policy:

```txt
fail_run            The bridge raises on failed/denied results unless the
                    failure is a non-terminal pause such as approval.

return_recoverable  The bridge may return recoverable failures to the model
                    when the result carries `recovery.recoverable == true`.
```

This keeps backward compatibility while moving detailed recoverability from
tool-name-specific bridge logic into typed tool results.

## Model-visible Payload

The bridge must not expose raw audit records, authorization internals, secrets,
or oversized provider output to the model. It should return a compact safe
payload:

```json
{
  "status": "failed",
  "recoverable": true,
  "failure_kind": "invalid_input",
  "message": "Path is outside allowed workspace paths.",
  "guidance": "Retry with an absolute path under /artifacts.",
  "suggested_input": {
    "path": "/artifacts/surprise.html"
  },
  "allowed_values": {
    "allowed_paths": ["/artifacts"]
  }
}
```

The stream event may contain richer policy-safe metadata, but model-visible
payloads should be minimal and redacted.

## Recovery Budget

Recovery must have a small explicit budget.

First implementation:

```txt
budget key = run_id + tool_name + recovery.attempt_key
default max_attempts = recovery.max_attempts, defaulting to 2
```

If `attempt_key` is absent, use:

```txt
tool_name + ":" + failure_kind
```

The bridge computes attempts by reading prior recovery events for the run. This
makes the budget durable across pause/resume and keeps the model prompt from
being the source of truth.

When the budget allows recovery:

```txt
tool.failed or tool.denied
tool.recovery.offered
return compact recovery payload to model
```

When exhausted:

```txt
tool.failed or tool.denied
tool.recovery.exhausted
raise AgentError("TOOL_FAILED", ...)
```

## Event Payloads

`tool.failed` and `tool.denied` should include safe recovery metadata when
present:

```json
{
  "tool_call_id": "tool_call_1",
  "tool_name": "workspace.write_file",
  "status": "denied",
  "error": {
    "message": "Path is outside allowed workspace paths: index.html"
  },
  "recovery": {
    "recoverable": true,
    "kind": "invalid_input",
    "action": "retry_with_corrected_input",
    "message": "Path is outside allowed workspace paths.",
    "model_guidance": "Use an absolute workspace path under /artifacts.",
    "suggested_input": {
      "path": "/artifacts/index.html"
    },
    "allowed_values": {
      "allowed_paths": ["/artifacts"]
    },
    "attempt_key": "workspace_path_policy",
    "max_attempts": 2
  },
  "recovery_attempt": {
    "attempt": 1,
    "max_attempts": 2,
    "attempt_key": "workspace.write_file:workspace_path_policy"
  }
}
```

`tool.recovery.offered` should be debug/audit visible and include:

- `tool_call_id`
- `tool_name`
- `attempt_key`
- `attempt`
- `max_attempts`
- `failure_kind`
- `action`

`tool.recovery.exhausted` should include the same fields plus the final error.

## Adapter Responsibilities

Adapters classify expected failures as close to the domain as possible.

Workspace examples:

- Bare path or path outside allowed workspace roots:
  `invalid_input`, `retry_with_corrected_input`, suggested absolute path.
- Missing file on read:
  `not_found`, guidance to list workspace files or choose another path.
- Missing write scope:
  `policy_denied`, not recoverable.

Sandbox examples:

- Invalid file operation request:
  `invalid_input`, include Pydantic validation details only when safe.
- Python execution non-zero exit:
  `execution_failed`, guidance to inspect stdout/stderr and adjust code.
- Sandbox disabled by skill policy:
  `policy_denied`, not recoverable.

Web examples:

- Search/fetch provider timeout:
  `transient`, action `wait_or_degrade`.
- Unsupported URL or malformed URL:
  `invalid_input`, action `retry_with_corrected_input`.

External/workflow capability examples:

- Provider-owned approval requirement:
  `approval_required`, action `require_approval`.
- Provider terminal failure with safe fallback:
  `transient` or `execution_failed`, action `wait_or_degrade` only if the
  descriptor allows recoverable failures.
- Missing external permission:
  `policy_denied`, not recoverable.

## Bridge Responsibilities

The Pydantic AI bridge owns the model-facing recovery decision:

1. Emit `tool.proposed` before prepare when the call is model-originated.
2. Emit prepare denials as `tool.denied`.
3. Execute allowed calls through the Capability Router.
4. Emit `tool.completed`, `tool.failed`, or `tool.denied`.
5. If the result is failed/denied and has recoverable metadata:
   - check descriptor `failure_policy`;
   - check the recovery budget;
   - emit `tool.recovery.offered`;
   - return compact recovery payload to the model.
6. If the result is failed/denied and not recoverable:
   - raise `AgentError("TOOL_FAILED", message)`.

The bridge should not contain tool-name-specific recovery rules except as a
temporary compatibility path during migration.

## Worker Responsibilities

The worker remains responsible for terminal run handling, infrastructure retry,
pause/resume, and cancellation. It should not become the LLM correction loop.

Existing worker-level retry may still requeue a run after infrastructure
exceptions, but it must not be used to correct tool arguments. Tool argument
correction happens inside the active model/tool interaction by returning a
recoverable tool result.

## Compatibility And Migration

First phase:

- Add the typed recovery contract with default `None`.
- Keep existing `failure_policy` values.
- Keep current web and workspace-path behavior while adding tests for the new
  generic path.

Second phase:

- Move web recoverable failures from `ResearchRecoverableToolFailure` bridge
  special cases into `AgentToolRecovery`.
- Move workspace path recovery into the workspace adapter result.
- Convert validation-denied local tool results to typed recoveries where safe.

Third phase:

- Remove tool-name-specific recovery branching from the bridge.
- Use a single generic function to decide whether to return recovery to the
  model or raise.

## Testing Strategy

Unit tests:

- `AgentToolRecovery` serializes with stable enum values.
- `AgentToolCallResult` remains backward compatible when `recovery` is absent.
- Helper constructors produce recoverable invalid-input and nonrecoverable
  policy-denied results.
- Recovery attempt keys are stable.

Bridge tests:

- A recoverable failed result is emitted as `tool.failed`, followed by
  `tool.recovery.offered`, and returned to the model.
- A nonrecoverable failed result raises `TOOL_FAILED`.
- A recoverable result with `failure_policy = fail_run` raises `TOOL_FAILED`.
- Recovery budget exhaustion emits `tool.recovery.exhausted` and fails the run.
- Model-visible payload omits audit and authorization internals.

Integration tests:

- A model first calls `workspace.write_file` with `index.html`; the tool returns
  a recoverable invalid-input path failure; the model retries with
  `/artifacts/index.html`; the run completes.
- A model hits a missing workspace file, lists files, retries a valid read, and
  completes.
- A policy denial does not return a retry suggestion and ends as `run.failed`.
- Existing web recoverable failure tests continue to pass during migration.

Verification:

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

## Acceptance Criteria

The design is implemented when:

- Recoverable tool failures are represented by typed `AgentToolRecovery`
  metadata.
- The bridge uses generic recovery metadata instead of tool-name-specific
  recovery rules for at least workspace path correction.
- Recoverable failures are returned to the model only when descriptor policy and
  retry budget allow it.
- Nonrecoverable policy, approval, and fatal failures cannot be retried by the
  model as a correction loop.
- Stream events explain offered and exhausted recovery attempts.
- The worker still fails terminal exceptions and does not own LLM correction.
- Backend tests and the file report example pass.
