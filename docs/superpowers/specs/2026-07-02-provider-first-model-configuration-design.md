# Provider and Model Configuration Design

Status: proposed

Date: 2026-07-02

## Summary

Model configuration should use first-class provider and model concepts.

A provider owns transport configuration: adapter kind, endpoint, compatibility
mode, and API key. A model belongs to one provider and owns the remote model ID,
display name, capabilities, and optional request defaults. Runs select a model
with a stable `provider_key/model_key` reference.

The previous "model profile" shape mixed provider credentials, endpoint
settings, and one model into a single record. This design replaces that model
rather than preserving it as the main abstraction.

## Goals

- Make DeepSeek setup clear and fast.
- Support custom OpenAI-compatible endpoints with multiple models under one
  provider.
- Let users understand configuration as `provider -> models`.
- Let chat selection display and store `provider/model`, similar to OpenCode.
- Store one provider API key once, not once per model.
- Support an explicit user-chosen default model without any built-in default.
- Keep the implementation small enough to fit the current Agent backend.

## Non-Goals

- No provider marketplace.
- No automatic model discovery.
- No Models.dev integration.
- No provider routing, fallback, load balancing, or scheduling.
- No workflow semantics.
- No long-lived compatibility layer for model profiles.

## Domain Model

### AgentModelProvider

Provider entries are scoped to org and owner user, matching the existing Agent
configuration ownership model.
Provider keys are stable slugs and must not contain `/` or whitespace.

```ts
type AgentModelProviderKind =
  | "openai_compatible"
  | "anthropic"
  | "test";

interface AgentModelProviderEntry {
  id: string;
  org_id: string;
  owner_user_id: string;
  key: string;
  name: string;
  kind: AgentModelProviderKind;
  enabled: boolean;
  base_url: string | null;
  compat: "deepseek" | "qwen" | "minimax" | "gemini_openai_compatible" | null;
  auth_secret: AgentSecretStatus | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}
```

The provider owns:

- API key secret reference;
- base URL;
- adapter family;
- provider-wide compatibility behavior.

### AgentModel

Model keys are unique inside one provider. The public model reference is
`${provider.key}/${model.key}`.
Model keys are stable slugs and must not contain `/` or whitespace.

```ts
interface AgentModelEntry {
  id: string;
  org_id: string;
  owner_user_id: string;
  provider_key: string;
  key: string;
  name: string;
  provider_model_id: string;
  enabled: boolean;
  capabilities: {
    vision: boolean;
    thinking: boolean;
  };
  request: Record<string, unknown> | null;
  cost_policy: AgentModelCostPolicy | null;
  selection_policy: AgentModelSelectionPolicy | null;
  created_at: string;
  updated_at: string;
}
```

The model owns:

- the ID sent to the provider API, such as `deepseek-v4-flash`;
- user-facing model name;
- feature capabilities;
- per-model request defaults.

## API

Replace `/api/model-profiles` in frontend and runtime code with:

```txt
GET    /api/model-providers
POST   /api/model-providers
GET    /api/model-providers/:provider_key
PATCH  /api/model-providers/:provider_key
DELETE /api/model-providers/:provider_key

GET    /api/model-providers/:provider_key/models
POST   /api/model-providers/:provider_key/models
GET    /api/model-providers/:provider_key/models/:model_key
PATCH  /api/model-providers/:provider_key/models/:model_key
DELETE /api/model-providers/:provider_key/models/:model_key

GET    /api/model-default
PUT    /api/model-default
```

`GET /api/model-providers` may include each provider's models so settings and
chat can render with one request.

Deletes are real deletes for configuration records. Historical runs keep their
stored `model_ref` string for display, but deleted models cannot be selected for
new runs.
Deleting the currently default model clears the default model setting.

`PUT /api/model-default` accepts `{ "model_ref": "provider/model" }` or
`{ "model_ref": null }`. Setting a default validates that the referenced
provider and model exist, are enabled, and are owned by the current user.

## Secret Handling

Provider API keys are stored once:

```txt
secret://model-providers/{org_id}/{owner_user_id}/{provider_key}/api-key
```

Responses only return redacted secret status. Write requests accept the same
write-only secret input pattern used elsewhere:

```json
{
  "auth_secret": {
    "write_only_value": "sk-..."
  }
}
```

Models never store secrets.

## Runtime Selection

Run harness options should move from `model_profile_key` to `model_ref`:

```json
{
  "model_ref": "deepseek/deepseek-v4-flash"
}
```

The runtime resolver:

1. Parses `provider_key/model_key`.
2. Loads the provider and model in the run's org/user scope.
3. Fails with `MODEL_NOT_CONFIGURED` if no model is selected.
4. Fails with `MODEL_PROVIDER_NOT_FOUND` or `MODEL_NOT_FOUND` when missing.
5. Fails when provider or model is disabled.
6. Loads the provider API key, except for `test` providers.
7. Builds the adapter from provider transport settings plus model request
   settings.

The SDK adapter input should receive:

- provider kind;
- API key;
- `model.provider_model_id`;
- capabilities from the model;
- metadata merged from provider compatibility settings and model request
  defaults.

## Default Selection

The default model is stored as an optional setting, not as a boolean on model
rows:

```txt
model.default_ref.{owner_user_id} = deepseek/deepseek-v4-flash
```

Unauthenticated local mode may use `model.default_ref`. Hosted/user-scoped
requests must use the owner-scoped key so users in the same org do not affect
each other's default model. There is no built-in default. If the setting is
missing or points to a disabled or deleted model, chat shows the no-model state
until the user chooses another model.

The settings UI may expose "Set as default" on each model row. The chat UI may
read this setting, but changing the model for one chat run does not mutate the
global default.

## Presets

Presets are creation shortcuts, not separate runtime concepts.

### DeepSeek

Creates one provider:

```json
{
  "key": "deepseek",
  "name": "DeepSeek",
  "kind": "openai_compatible",
  "base_url": "https://api.deepseek.com",
  "compat": "deepseek"
}
```

Creates initial models:

```txt
deepseek-v4-flash
deepseek-v4-pro
```

`deepseek-chat` and `deepseek-reasoner` should not be defaults because DeepSeek
documents them as deprecated on 2026-07-24 15:59 UTC.

### Custom OpenAI-Compatible

Creates one provider with:

- user-provided key/name;
- `kind: "openai_compatible"`;
- user-provided base URL;
- user-provided API key.

The user manually adds model IDs under that provider.

## Settings UX

Rename the settings section from "Model profiles" to "Models".

The page should have:

- a provider list;
- a selected provider detail panel;
- a models table for the selected provider.

Empty state:

- `Add DeepSeek`
- `Add OpenAI-compatible provider`

Provider form:

- name;
- key;
- kind;
- base URL;
- API key;
- enabled.

Model table:

- model key;
- provider model ID;
- display name;
- enabled;
- vision;
- thinking;
- set as default.

This is an operational settings screen, not a marketing onboarding wizard.

## Chat UX

The composer lists configured enabled models grouped by provider:

```txt
DeepSeek
  deepseek-v4-flash
  deepseek-v4-pro

My Gateway
  qwen3-coder
  kimi-k2
```

Selecting a row stores `model_ref`. If no enabled model exists, the composer
keeps the explicit no-model state and blocks sending.

## Migration

Model profiles are legacy data after this change.

Implementation can include a one-time migration from `model_profile_entry` to:

- one provider per distinct provider/base URL/owner group;
- one model per old profile;
- one provider secret copied from the old profile secret when present.

After migration, runtime and frontend should read provider/model records, not
model profiles. Model profile routes do not need to remain public product API.

## Persistence

SQLite should store provider/model records in dedicated document tables:

```txt
model_providers
model_entries
```

Both tables follow the existing document-table pattern:

```txt
id TEXT PRIMARY KEY
org_id TEXT
owner_user_id TEXT
key TEXT
payload TEXT NOT NULL
```

For model rows, `key` should be the full `provider_key/model_key` reference so
lookup and uniqueness stay simple.

The selected default model uses the existing settings store under
`model.default_ref.{owner_user_id}` for authenticated users.

## Tests

Backend:

- provider create/list/update/delete with org/user isolation;
- model create/list/update/delete under a provider;
- provider secret is redacted in API responses;
- runtime resolves `model_ref` to provider plus model;
- runtime rejects missing, disabled, and secretless provider/model selections;
- DeepSeek preset payload maps to the OpenAI-compatible adapter;
- deleting the default model clears `model.default_ref`.

Frontend:

- empty settings state offers DeepSeek and custom OpenAI-compatible provider;
- one provider can contain multiple models;
- chat selector groups models by provider;
- no enabled model blocks sending;
- default selection is empty until the user sets a real model;
- saved run options contain `model_ref`, not `model_profile_key`.

## References

- OpenCode model/provider configuration:
  https://opencode.ai/docs/models/
- OpenCode config shape:
  https://opencode.ai/docs/config/
- DeepSeek API docs:
  https://api-docs.deepseek.com/
