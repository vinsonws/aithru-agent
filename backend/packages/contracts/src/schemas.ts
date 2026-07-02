import { Type, type Static } from "@sinclair/typebox";

// ── Enums ──────────────────────────────────────────────────────────────

export const AGENT_RUN_STATUSES = [
  "queued",
  "running",
  "waiting_approval",
  "waiting_subagent",
  "waiting_input",
  "waiting_external_run",
  "completed",
  "failed",
  "cancelled",
] as const;

export const AgentRunStatus = Type.Union(
  AGENT_RUN_STATUSES.map((s) => Type.Literal(s)) as any
);

export const TERMINAL_RUN_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
]);

export const RUN_STATUS_TRANSITIONS: Record<string, ReadonlySet<string>> = {
  queued: new Set(["running", "cancelled"]),
  running: new Set([
    "queued",
    "waiting_approval",
    "waiting_subagent",
    "waiting_input",
    "waiting_external_run",
    "completed",
    "failed",
    "cancelled",
  ]),
  waiting_approval: new Set(["queued", "running", "failed", "cancelled"]),
  waiting_subagent: new Set(["running", "failed", "cancelled"]),
  waiting_input: new Set(["queued", "running", "failed", "cancelled"]),
  waiting_external_run: new Set(["queued", "running", "failed", "cancelled"]),
  completed: new Set(),
  failed: new Set(),
  cancelled: new Set(),
};

export function validateRunStatusTransition(
  current: string,
  next: string,
): string {
  const currentStatus = current as (typeof AGENT_RUN_STATUSES)[number];
  const targetStatus = next as (typeof AGENT_RUN_STATUSES)[number];

  if (currentStatus === targetStatus) return targetStatus;
  if (TERMINAL_RUN_STATUSES.has(currentStatus)) {
    throw new Error(
      `INVALID_RUN_STATUS_TRANSITION: Cannot transition terminal run from ${currentStatus} to ${targetStatus}`,
    );
  }
  const allowed = RUN_STATUS_TRANSITIONS[currentStatus];
  if (!allowed || !allowed.has(targetStatus)) {
    throw new Error(
      `INVALID_RUN_STATUS_TRANSITION: Invalid run status transition from ${currentStatus} to ${targetStatus}`,
    );
  }
  return targetStatus;
}

export const AGENT_RUN_SOURCES = [
  "chat",
  "skill",
  "api",
  "workbench_node",
  "delegated_task",
] as const;

export const AgentRunSource = Type.Union(
  AGENT_RUN_SOURCES.map((s) => Type.Literal(s)) as any
);

export const AGENT_MESSAGE_ROLES = [
  "user",
  "assistant",
  "system",
  "tool",
] as const;

export const AgentMessageRole = Type.Union(
  AGENT_MESSAGE_ROLES.map((s) => Type.Literal(s)) as any
);

export const AGENT_THREAD_STATUSES = ["active", "archived"] as const;
export const AgentThreadStatus = Type.Union(
  AGENT_THREAD_STATUSES.map((s) => Type.Literal(s)) as any
);

// ── Stream types ───────────────────────────────────────────────────────

export const AgentStreamVisibility = Type.Union([
  Type.Literal("user"),
  Type.Literal("debug"),
  Type.Literal("audit"),
]);

export const AgentStreamRedaction = Type.Union([
  Type.Literal("none"),
  Type.Literal("partial"),
  Type.Literal("full"),
]);

export const AgentStreamSourceSchema = Type.Object({
  kind: Type.String(),
  id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  name: Type.Optional(Type.Union([Type.String(), Type.Null()])),
});

// ── Core domain schemas ────────────────────────────────────────────────

export const AgentThreadSchema = Type.Object({
  id: Type.String(),
  org_id: Type.String(),
  owner_user_id: Type.String(),
  title: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  status: AgentThreadStatus,
  created_at: Type.String(),
  updated_at: Type.String(),
});

export const AgentMessageSchema = Type.Object({
  id: Type.String(),
  org_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  actor_user_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  thread_id: Type.String(),
  role: AgentMessageRole,
  content: Type.String(),
  run_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  workspace_paths: Type.Array(Type.String()),
  created_at: Type.String(),
});

export const AgentRunHarnessOptionsSchema = Type.Object({
  model: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  model_profile_key: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  mode: Type.Optional(
    Type.Union([
      Type.Literal("flash"),
      Type.Literal("thinking"),
      Type.Literal("pro"),
      Type.Literal("ultra"),
      Type.Null(),
    ]),
  ),
  thinking_enabled: Type.Optional(Type.Union([Type.Boolean(), Type.Null()])),
  is_plan_mode: Type.Optional(Type.Union([Type.Boolean(), Type.Null()])),
  subagent_enabled: Type.Optional(Type.Union([Type.Boolean(), Type.Null()])),
  instructions: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  model_capabilities: Type.Optional(
    Type.Union([
      Type.Object({
        vision: Type.Optional(Type.Boolean()),
        thinking: Type.Optional(Type.Boolean()),
      }),
      Type.Null(),
    ]),
  ),
  model_reasoning_effort: Type.Optional(
    Type.Union([
      Type.Literal("none"),
      Type.Literal("low"),
      Type.Literal("medium"),
      Type.Literal("high"),
      Type.Null(),
    ]),
  ),
});

export const AgentRunClaimSchema = Type.Object({
  worker_id: Type.String(),
  claimed_at: Type.String(),
  last_heartbeat_at: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  lease_expires_at: Type.String(),
  attempt: Type.Number(),
});

export const AgentRunResultSchema = Type.Object({
  content: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  workspace_paths: Type.Array(Type.String()),
  message_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  thread_message_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
});

export const AgentRunRetryPolicySchema = Type.Object({
  max_attempts: Type.Number(),
  initial_delay_seconds: Type.Number(),
  max_delay_seconds: Type.Number(),
  backoff_multiplier: Type.Number(),
});

export const AgentRunRetryStateSchema = Type.Object({
  attempt: Type.Number(),
  next_retry_at: Type.Union([Type.String(), Type.Null()]),
  last_error: Type.Optional(Type.Object({
    code: Type.String(),
    message: Type.String(),
  })),
});

export const AgentRunSchema = Type.Object({
  id: Type.String(),
  org_id: Type.String(),
  actor_user_id: Type.String(),
  source: AgentRunSource,
  thread_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  workspace_id: Type.String(),
  task_msg: Type.String(),
  scopes: Type.Array(Type.String()),
  harness_options: Type.Optional(
    Type.Union([AgentRunHarnessOptionsSchema, Type.Null()])
  ),
  status: AgentRunStatus,
  current_approval_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  started_at: Type.String(),
  completed_at: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  claim: Type.Optional(Type.Union([AgentRunClaimSchema, Type.Null()])),
  retry_policy: Type.Optional(Type.Union([AgentRunRetryPolicySchema, Type.Null()])),
  retry_state: Type.Optional(Type.Union([AgentRunRetryStateSchema, Type.Null()])),
  result: Type.Optional(Type.Union([AgentRunResultSchema, Type.Null()])),
  error: Type.Optional(Type.Unknown()),
}, { additionalProperties: false });

export const AgentStreamEventSchema = Type.Object({
  id: Type.String(),
  org_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  actor_user_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  run_id: Type.String(),
  thread_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  sequence: Type.Number(),
  timestamp: Type.String(),
  type: Type.String(),
  source: AgentStreamSourceSchema,
  visibility: AgentStreamVisibility,
  redaction: AgentStreamRedaction,
  summary: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  payload: Type.Unknown(),
});

export const HealthResponseSchema = Type.Object({
  status: Type.String(),
  version: Type.String(),
});

// ── API request schemas ────────────────────────────────────────────────

export const CreateThreadRequestSchema = Type.Object({
  org_id: Type.String(),
  owner_user_id: Type.String(),
  title: Type.Optional(Type.String()),
});

export const UpdateThreadRequestSchema = Type.Object({
  title: Type.Optional(Type.String()),
  status: Type.Optional(AgentThreadStatus),
});

export const CreateMessageRequestSchema = Type.Object({
  role: AgentMessageRole,
  content: Type.String(),
  run_id: Type.Optional(Type.String()),
});

export const CreateRunRequestSchema = Type.Object({
  org_id: Type.String(),
  actor_user_id: Type.String(),
  source: Type.Optional(AgentRunSource),
  thread_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  task_msg: Type.String(),
  scopes: Type.Optional(Type.Union([Type.Array(Type.String()), Type.Null()])),
  selected_skill_keys: Type.Optional(Type.Union([Type.Array(Type.String()), Type.Null()])),
  harness_options: Type.Optional(
    Type.Union([Type.Record(Type.String(), Type.Unknown()), Type.Null()])
  ),
  wait_for_completion: Type.Optional(Type.Boolean()),
  persist_task_msg_message: Type.Optional(Type.Boolean()),
}, { additionalProperties: false });
