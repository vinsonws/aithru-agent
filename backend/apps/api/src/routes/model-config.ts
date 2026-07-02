import { createHash } from "node:crypto";
import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getRuntime } from "../runtime.js";
import { platformActorFromRequest, requestActorUserId, requestOrgId as platformRequestOrgId } from "../platform-auth.js";

const DEFAULT_REF_SETTING = "model.default_ref";

type ModelProviderEntry = {
  id: string;
  org_id: string;
  owner_user_id: string;
  key: string;
  name: string;
  kind: string;
  enabled: boolean;
  base_url: string | null;
  compat: string | null;
  auth_secret: ReturnType<typeof secretStatus> | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

type ModelEntry = {
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
  context_window_tokens: number | null;
  request: Record<string, unknown> | null;
  cost_policy: Record<string, unknown> | null;
  selection_policy: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export function modelRef(providerKey: string, modelKey: string): string {
  return `${providerKey}/${modelKey}`;
}

export function isValidModelKey(value: string): boolean {
  return /^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(value);
}

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function params(request: FastifyRequest): Record<string, string> {
  return (request.params ?? {}) as Record<string, string>;
}

function requestOrgId(request: FastifyRequest, body?: any): string {
  return platformRequestOrgId(platformActorFromRequest(request), body, request.query as any);
}

function requestOwnerUserId(request: FastifyRequest, body?: any): string {
  return requestActorUserId(platformActorFromRequest(request), body);
}

function ownerScopeForRequest(request: FastifyRequest, body?: any): string | undefined {
  return platformActorFromRequest(request) ? requestOwnerUserId(request, body) : undefined;
}

function defaultRefSettingKey(ownerUserId?: string): string {
  return ownerUserId ? `${DEFAULT_REF_SETTING}.${ownerUserId}` : DEFAULT_REF_SETTING;
}

function idFor(prefix: string, orgId: string, ownerUserId: string | undefined, key: string): string {
  const digest = createHash("sha256")
    .update(ownerUserId ? `${orgId}\0${ownerUserId}\0${key}` : `${orgId}\0${key}`)
    .digest("hex")
    .slice(0, 20);
  return `${prefix}_${digest}`;
}

function secretStatus(secretRef: string | null = null) {
  return secretRef
    ? { has_secret: true, secret_ref: secretRef, redacted: true }
    : { has_secret: false, secret_ref: null, redacted: true };
}

function providerSecretRef(orgId: string, ownerUserId: string | undefined, providerKey: string): string {
  return ownerUserId
    ? `secret://model-providers/${orgId}/${ownerUserId}/${providerKey}/api-key`
    : `secret://model-providers/${orgId}/${providerKey}/api-key`;
}

function badRequest(reply: FastifyReply, message: string) {
  reply.code(400);
  return { error: message };
}

function optionalPositiveInteger(value: unknown): number | null {
  if (value == null || value === "") return null;
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : NaN;
}

function notFound(reply: FastifyReply, message: string) {
  reply.code(404);
  return { error: message };
}

function conflict(reply: FastifyReply, message: string) {
  reply.code(409);
  return { error: message };
}

function documentWriteGuard(request: FastifyRequest, body?: any) {
  const actor = platformActorFromRequest(request);
  return {
    orgId: requestOrgId(request, body),
    ...(actor ? { ownerUserId: requestOwnerUserId(request, body) } : {}),
  };
}

function documentPayload<T>(kind: string, id: string): T | null {
  return (getRuntime().store.getDocument(kind, id)?.payload as T | undefined) ?? null;
}

function listDocumentPayloads<T>(kind: string, orgId: string): T[] {
  return getRuntime().store.listDocuments(kind, orgId).map((doc) => doc.payload as T);
}

function publicModel(model: ModelEntry): ModelEntry {
  return { ...model, context_window_tokens: model.context_window_tokens ?? null };
}

function providerByKey(orgId: string, providerKey: string, ownerUserId?: string): ModelProviderEntry | null {
  return listDocumentPayloads<ModelProviderEntry>("model_provider_entry", orgId).find(
    (provider) => provider.key === providerKey && (!ownerUserId || provider.owner_user_id === ownerUserId),
  ) ?? null;
}

function modelByKey(orgId: string, providerKey: string, key: string, ownerUserId?: string): ModelEntry | null {
  return listDocumentPayloads<ModelEntry>("model_entry", orgId).find(
    (model) =>
      model.provider_key === providerKey &&
      model.key === key &&
      (!ownerUserId || model.owner_user_id === ownerUserId),
  ) ?? null;
}

function modelsForProvider(orgId: string, providerKey: string, ownerUserId?: string): ModelEntry[] {
  return listDocumentPayloads<ModelEntry>("model_entry", orgId)
    .filter(
      (model) =>
        model.provider_key === providerKey &&
        (!ownerUserId || model.owner_user_id === ownerUserId),
    )
    .sort((a, b) => a.key.localeCompare(b.key));
}

function resolveProviderSecret(input: any, orgId: string, providerKey: string, ownerUserId?: string) {
  if (!input) return null;
  if (input.write_only_value != null) {
    if (typeof input.write_only_value !== "string" || !input.write_only_value.trim()) {
      throw new Error("write_only_value must be a nonblank string");
    }
    const ref = providerSecretRef(orgId, ownerUserId, providerKey);
    getRuntime().store.setSecret(orgId, ref, input.write_only_value);
    return secretStatus(ref);
  }
  if (typeof input.secret_ref === "string" && input.secret_ref.trim()) {
    throw new Error("secret_ref is read-only");
  }
  return secretStatus();
}

function defaultModelRefForOrg(orgId: string, ownerUserId?: string): string | null {
  const value = getRuntime().store.getSetting(orgId, defaultRefSettingKey(ownerUserId));
  return value ? value : null;
}

function clearDefaultModelIfSelected(orgId: string, ownerUserId: string | undefined, value: string): void {
  const settingKeys = new Set([defaultRefSettingKey(ownerUserId), DEFAULT_REF_SETTING]);
  for (const settingKey of settingKeys) {
    if (getRuntime().store.getSetting(orgId, settingKey) === value) {
      getRuntime().store.setSetting(orgId, settingKey, "");
    }
  }
}

function parseModelRef(value: string): { providerKey: string; modelKey: string } | null {
  const slash = value.indexOf("/");
  if (slash <= 0 || slash === value.length - 1) return null;
  const providerKey = value.slice(0, slash);
  const modelKey = value.slice(slash + 1);
  return isValidModelKey(providerKey) && isValidModelKey(modelKey) ? { providerKey, modelKey } : null;
}

function stripKnownModelPrefix(value: string): string {
  return value.replace(/^(custom|openai|anthropic|test):/, "").trim();
}

function slugifyKey(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "model";
}

function humanizeName(value: string): string {
  return stripKnownModelPrefix(value).replace(/[-_]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

type LegacyModelProfile = {
  id?: string;
  org_id?: string;
  owner_user_id?: string;
  key?: string;
  name?: string;
  provider?: string;
  model?: string;
  enabled?: boolean;
  auth_secret?: ReturnType<typeof secretStatus> | null;
  metadata?: {
    base_url?: string | null;
    compat?: string | null;
    request?: Record<string, unknown> | null;
  } | null;
  capabilities?: ModelEntry["capabilities"] | null;
  cost_policy?: Record<string, unknown> | null;
  selection_policy?: Record<string, unknown> | null;
};

type LegacyProviderGroup = {
  kind: ModelProviderEntry["kind"];
  baseUrl: string | null;
  compat: string | null;
  profiles: LegacyModelProfile[];
};

function normalizedLegacyProviderKind(provider: string | undefined): ModelProviderEntry["kind"] {
  return provider === "anthropic"
    ? "anthropic"
    : provider === "test"
      ? "test"
      : "openai_compatible";
}

function legacyProviderGroupId(profile: LegacyModelProfile): string {
  const kind = normalizedLegacyProviderKind(profile.provider);
  const baseUrl = typeof profile.metadata?.base_url === "string" ? profile.metadata.base_url : "";
  const compat = typeof profile.metadata?.compat === "string" ? profile.metadata.compat : "";
  return `${kind}\0${baseUrl}\0${compat}`;
}

function legacyProviderBaseKey(group: LegacyProviderGroup): string {
  return group.compat === "deepseek"
    ? "deepseek"
    : slugifyKey(
        group.kind === "anthropic"
          ? "anthropic"
          : group.kind === "test"
            ? "test"
            : "custom",
      );
}

function legacyProviderKey(group: LegacyProviderGroup, groupCountForBaseKey: number): string {
  if (group.compat === "deepseek") return "deepseek";
  const baseKey = legacyProviderBaseKey(group);
  if (groupCountForBaseKey <= 1) return baseKey;
  return slugifyKey(
    `${baseKey}-${group.compat ?? "default"}-${group.baseUrl ?? "default"}`,
  );
}

function stableLegacyProfileSort(a: LegacyModelProfile, b: LegacyModelProfile): number {
  return `${a.key ?? ""}\0${a.id ?? ""}`.localeCompare(`${b.key ?? ""}\0${b.id ?? ""}`);
}

function migrateLegacyModelProfilesForRequest(request: FastifyRequest): void {
  const store = getRuntime().store;
  const orgId = requestOrgId(request);
  const ownerUserId = requestOwnerUserId(request);
  const existing = store
    .listDocuments("model_provider_entry", orgId)
    .some((doc) => (doc.payload as any).owner_user_id === ownerUserId);
  if (existing) return;

  const profiles = store
    .listDocuments("model_profile_entry", orgId)
    .map((doc) => doc.payload as LegacyModelProfile)
    .filter((profile) => profile.owner_user_id === ownerUserId && typeof profile.model === "string" && profile.model.trim());

  const groups = new Map<string, LegacyProviderGroup>();
  for (const profile of profiles) {
    const groupId = legacyProviderGroupId(profile);
    const existingGroup = groups.get(groupId);
    if (existingGroup) {
      existingGroup.profiles.push(profile);
      continue;
    }
    groups.set(groupId, {
      kind: normalizedLegacyProviderKind(profile.provider),
      baseUrl: typeof profile.metadata?.base_url === "string" ? profile.metadata.base_url : null,
      compat: typeof profile.metadata?.compat === "string" ? profile.metadata.compat : null,
      profiles: [profile],
    });
  }

  const grouped = [...groups.values()].sort((a, b) =>
    `${legacyProviderBaseKey(a)}\0${a.compat ?? ""}\0${a.baseUrl ?? ""}`.localeCompare(
      `${legacyProviderBaseKey(b)}\0${b.compat ?? ""}\0${b.baseUrl ?? ""}`,
    ),
  );
  const baseKeyCounts = new Map<string, number>();
  for (const group of grouped) {
    const baseKey = legacyProviderBaseKey(group);
    baseKeyCounts.set(baseKey, (baseKeyCounts.get(baseKey) ?? 0) + 1);
  }

  for (const group of grouped) {
    group.profiles.sort(stableLegacyProfileSort);
    const providerKey = legacyProviderKey(group, baseKeyCounts.get(legacyProviderBaseKey(group)) ?? 1);
    const providerId = idFor("model_provider", orgId, ownerUserId, providerKey);
    const timestamp = now();
    const secretProfile = group.profiles.find(
      (profile) => profile.auth_secret?.has_secret || profile.auth_secret?.secret_ref,
    );
    store.upsertDocument("model_provider_entry", providerId, {
      id: providerId,
      org_id: orgId,
      owner_user_id: ownerUserId,
      key: providerKey,
      name: providerKey === "deepseek" ? "DeepSeek" : humanizeName(providerKey),
      kind: group.kind,
      enabled: group.profiles.some((profile) => profile.enabled !== false),
      base_url: group.baseUrl,
      compat: group.compat,
      auth_secret: secretProfile?.auth_secret ?? secretStatus(),
      metadata: null,
      created_at: timestamp,
      updated_at: timestamp,
    });

    const usedModelKeys = new Set<string>();
    for (const profile of group.profiles) {
      const strippedModel = stripKnownModelPrefix(String(profile.model));
      const modelKey = slugifyKey(strippedModel);
      let uniqueModelKey = modelKey;
      for (let suffix = 2; usedModelKeys.has(uniqueModelKey); suffix += 1) {
        uniqueModelKey = `${modelKey}-${suffix}`;
      }
      usedModelKeys.add(uniqueModelKey);
      store.upsertDocument("model_entry", idFor("model_entry", orgId, ownerUserId, `${providerKey}/${uniqueModelKey}`), {
        id: idFor("model_entry", orgId, ownerUserId, `${providerKey}/${uniqueModelKey}`),
        org_id: orgId,
        owner_user_id: ownerUserId,
        provider_key: providerKey,
        key: uniqueModelKey,
        name: profile.name ?? humanizeName(strippedModel),
        provider_model_id: strippedModel,
        enabled: profile.enabled !== false,
        capabilities: profile.capabilities ?? { vision: false, thinking: false },
        context_window_tokens: null,
        request: profile.metadata?.request ?? null,
        cost_policy: profile.cost_policy ?? null,
        selection_policy: profile.selection_policy ?? null,
        created_at: timestamp,
        updated_at: timestamp,
      });
    }
  }
}

function requireValidProviderKey(request: FastifyRequest, reply: FastifyReply): string | null {
  const providerKey = params(request).provider_key;
  return isValidModelKey(providerKey) ? providerKey : badRequest(reply, "Invalid provider key") && null;
}

function requireValidModelKey(request: FastifyRequest, reply: FastifyReply): string | null {
  const modelKey = params(request).model_key;
  return isValidModelKey(modelKey) ? modelKey : badRequest(reply, "Invalid model key") && null;
}

function providerWithModels(provider: ModelProviderEntry, orgId: string): ModelProviderEntry & { models: ModelEntry[]; default_model_ref?: string | null } {
  const defaultRef = defaultModelRefForOrg(orgId, provider.owner_user_id);
  return {
    ...provider,
    models: modelsForProvider(orgId, provider.key, provider.owner_user_id).map(publicModel),
    ...(defaultRef?.startsWith(`${provider.key}/`) ? { default_model_ref: defaultRef } : {}),
  };
}

async function listProviders(request: FastifyRequest) {
  migrateLegacyModelProfilesForRequest(request);
  const orgId = requestOrgId(request);
  const ownerUserId = ownerScopeForRequest(request);
  return listDocumentPayloads<ModelProviderEntry>("model_provider_entry", orgId)
    .filter((provider) => !ownerUserId || provider.owner_user_id === ownerUserId)
    .sort((a, b) => a.key.localeCompare(b.key))
    .map((provider) => providerWithModels(provider, orgId));
}

async function createProvider(request: FastifyRequest, reply: FastifyReply) {
  const body = (request.body ?? {}) as any;
  const orgId = requestOrgId(request, body);
  const ownerUserId = requestOwnerUserId(request, body);
  const ownerScope = ownerScopeForRequest(request, body);
  const key = String(body.key ?? "").trim();
  if (!isValidModelKey(key)) return badRequest(reply, "Invalid provider key");
  if (providerByKey(orgId, key, ownerScope)) return conflict(reply, "Model provider already exists");
  const timestamp = now();
  let authSecret = null;
  try {
    authSecret =
      Object.prototype.hasOwnProperty.call(body, "auth_secret")
        ? resolveProviderSecret(body.auth_secret, orgId, key, ownerScope)
        : secretStatus();
  } catch (error) {
    return badRequest(reply, error instanceof Error ? error.message : "Invalid provider secret");
  }
  const provider: ModelProviderEntry = {
    id: idFor("model_provider", orgId, ownerScope, key),
    org_id: orgId,
    owner_user_id: ownerUserId,
    key,
    name: String(body.name ?? key),
    kind: String(body.kind ?? "openai_compatible"),
    enabled: body.enabled ?? true,
    base_url: typeof body.base_url === "string" ? body.base_url : body.base_url ?? null,
    compat: typeof body.compat === "string" ? body.compat : body.compat ?? null,
    auth_secret: authSecret,
    metadata: body.metadata && typeof body.metadata === "object" ? body.metadata : body.metadata ?? null,
    created_at: timestamp,
    updated_at: timestamp,
  };
  getRuntime().store.insertDocument("model_provider_entry", provider.id, provider, documentWriteGuard(request, body));
  reply.code(201);
  return providerWithModels(provider, orgId);
}

async function getProvider(request: FastifyRequest, reply: FastifyReply) {
  const providerKey = requireValidProviderKey(request, reply);
  if (!providerKey) return reply.sent ? undefined : badRequest(reply, "Invalid provider key");
  const orgId = requestOrgId(request);
  const provider = providerByKey(orgId, providerKey, ownerScopeForRequest(request));
  return provider ? providerWithModels(provider, orgId) : notFound(reply, "Model provider not found");
}

async function updateProvider(request: FastifyRequest, reply: FastifyReply) {
  const providerKey = requireValidProviderKey(request, reply);
  if (!providerKey) return reply.sent ? undefined : badRequest(reply, "Invalid provider key");
  const body = (request.body ?? {}) as any;
  const orgId = requestOrgId(request);
  const ownerScope = ownerScopeForRequest(request);
  const provider = providerByKey(orgId, providerKey, ownerScope);
  if (!provider) return notFound(reply, "Model provider not found");
  if (Object.prototype.hasOwnProperty.call(body, "key") && String(body.key ?? provider.key).trim() !== provider.key) {
    return badRequest(reply, "Provider key cannot be changed");
  }
  let authSecret = provider.auth_secret;
  try {
    if (Object.prototype.hasOwnProperty.call(body, "auth_secret")) {
      authSecret = resolveProviderSecret(body.auth_secret, orgId, provider.key, ownerScope);
    }
  } catch (error) {
    return badRequest(reply, error instanceof Error ? error.message : "Invalid provider secret");
  }
  const updated: ModelProviderEntry = {
    ...provider,
    ...body,
    id: provider.id,
    org_id: provider.org_id,
    owner_user_id: provider.owner_user_id,
    key: provider.key,
    auth_secret: authSecret,
    updated_at: now(),
  };
  getRuntime().store.upsertDocument("model_provider_entry", provider.id, updated, documentWriteGuard(request, body));
  return providerWithModels(updated, orgId);
}

async function deleteProvider(request: FastifyRequest, reply: FastifyReply) {
  const providerKey = requireValidProviderKey(request, reply);
  if (!providerKey) return reply.sent ? undefined : badRequest(reply, "Invalid provider key");
  const orgId = requestOrgId(request);
  const ownerScope = ownerScopeForRequest(request);
  const provider = providerByKey(orgId, providerKey, ownerScope);
  if (!provider) return notFound(reply, "Model provider not found");
  const models = modelsForProvider(orgId, provider.key, ownerScope);
  for (const model of models) {
    clearDefaultModelIfSelected(orgId, provider.owner_user_id, modelRef(provider.key, model.key));
    getRuntime().store.deleteDocument("model_entry", model.id, documentWriteGuard(request));
  }
  getRuntime().store.deleteDocument("model_provider_entry", provider.id, documentWriteGuard(request));
  return { deleted: true };
}

async function listModels(request: FastifyRequest, reply: FastifyReply) {
  const providerKey = requireValidProviderKey(request, reply);
  if (!providerKey) return reply.sent ? undefined : badRequest(reply, "Invalid provider key");
  const orgId = requestOrgId(request);
  const ownerScope = ownerScopeForRequest(request);
  if (!providerByKey(orgId, providerKey, ownerScope)) return notFound(reply, "Model provider not found");
  return modelsForProvider(orgId, providerKey, ownerScope).map(publicModel);
}

async function createModel(request: FastifyRequest, reply: FastifyReply) {
  const providerKey = requireValidProviderKey(request, reply);
  if (!providerKey) return reply.sent ? undefined : badRequest(reply, "Invalid provider key");
  const body = (request.body ?? {}) as any;
  const orgId = requestOrgId(request, body);
  const ownerUserId = requestOwnerUserId(request, body);
  const ownerScope = ownerScopeForRequest(request, body);
  if (!providerByKey(orgId, providerKey, ownerScope)) return notFound(reply, "Model provider not found");
  const key = String(body.key ?? "").trim();
  if (!isValidModelKey(key)) return badRequest(reply, "Invalid model key");
  if (modelByKey(orgId, providerKey, key, ownerScope)) return conflict(reply, "Model already exists");
  const contextWindowTokens = optionalPositiveInteger(body.context_window_tokens);
  if (Number.isNaN(contextWindowTokens)) return badRequest(reply, "Invalid context_window_tokens");
  const timestamp = now();
  const model: ModelEntry = {
    id: idFor("model_entry", orgId, ownerScope, modelRef(providerKey, key)),
    org_id: orgId,
    owner_user_id: ownerUserId,
    provider_key: providerKey,
    key,
    name: String(body.name ?? key),
    provider_model_id: String(body.provider_model_id ?? key),
    enabled: body.enabled ?? true,
    capabilities: {
      vision: Boolean(body.capabilities?.vision),
      thinking: Boolean(body.capabilities?.thinking),
    },
    context_window_tokens: contextWindowTokens,
    request: body.request && typeof body.request === "object" ? body.request : body.request ?? null,
    cost_policy: body.cost_policy && typeof body.cost_policy === "object" ? body.cost_policy : body.cost_policy ?? null,
    selection_policy:
      body.selection_policy && typeof body.selection_policy === "object"
        ? body.selection_policy
        : body.selection_policy ?? null,
    created_at: timestamp,
    updated_at: timestamp,
  };
  getRuntime().store.insertDocument("model_entry", model.id, model, documentWriteGuard(request, body));
  reply.code(201);
  return publicModel(model);
}

async function getModel(request: FastifyRequest, reply: FastifyReply) {
  const providerKey = requireValidProviderKey(request, reply);
  if (!providerKey) return reply.sent ? undefined : badRequest(reply, "Invalid provider key");
  const modelKey = requireValidModelKey(request, reply);
  if (!modelKey) return reply.sent ? undefined : badRequest(reply, "Invalid model key");
  const orgId = requestOrgId(request);
  const model = modelByKey(orgId, providerKey, modelKey, ownerScopeForRequest(request));
  return model ? publicModel(model) : notFound(reply, "Model not found");
}

async function updateModel(request: FastifyRequest, reply: FastifyReply) {
  const providerKey = requireValidProviderKey(request, reply);
  if (!providerKey) return reply.sent ? undefined : badRequest(reply, "Invalid provider key");
  const modelKey = requireValidModelKey(request, reply);
  if (!modelKey) return reply.sent ? undefined : badRequest(reply, "Invalid model key");
  const body = (request.body ?? {}) as any;
  const orgId = requestOrgId(request);
  const ownerScope = ownerScopeForRequest(request);
  const model = modelByKey(orgId, providerKey, modelKey, ownerScope);
  if (!model) return notFound(reply, "Model not found");
  if (Object.prototype.hasOwnProperty.call(body, "key") && String(body.key ?? modelKey).trim() !== modelKey) {
    return badRequest(reply, "Model key cannot be changed");
  }
  const contextWindowTokens = Object.prototype.hasOwnProperty.call(body, "context_window_tokens")
    ? optionalPositiveInteger(body.context_window_tokens)
    : model.context_window_tokens;
  if (Number.isNaN(contextWindowTokens)) return badRequest(reply, "Invalid context_window_tokens");
  const updated: ModelEntry = {
    ...model,
    ...body,
    id: model.id,
    org_id: model.org_id,
    owner_user_id: model.owner_user_id,
    provider_key: model.provider_key,
    key: model.key,
    capabilities: {
      vision: body.capabilities?.vision ?? model.capabilities.vision,
      thinking: body.capabilities?.thinking ?? model.capabilities.thinking,
    },
    context_window_tokens: contextWindowTokens,
    updated_at: now(),
  };
  getRuntime().store.upsertDocument("model_entry", model.id, updated, documentWriteGuard(request, body));
  return publicModel(updated);
}

async function deleteModel(request: FastifyRequest, reply: FastifyReply) {
  const providerKey = requireValidProviderKey(request, reply);
  if (!providerKey) return reply.sent ? undefined : badRequest(reply, "Invalid provider key");
  const modelKey = requireValidModelKey(request, reply);
  if (!modelKey) return reply.sent ? undefined : badRequest(reply, "Invalid model key");
  const orgId = requestOrgId(request);
  const model = modelByKey(orgId, providerKey, modelKey, ownerScopeForRequest(request));
  if (!model) return notFound(reply, "Model not found");
  clearDefaultModelIfSelected(orgId, model.owner_user_id, modelRef(providerKey, modelKey));
  getRuntime().store.deleteDocument("model_entry", model.id, documentWriteGuard(request));
  return { deleted: true };
}

async function getDefaultModel(request: FastifyRequest) {
  return { model_ref: defaultModelRefForOrg(requestOrgId(request), ownerScopeForRequest(request)) };
}

async function setDefaultModel(request: FastifyRequest, reply: FastifyReply) {
  const body = (request.body ?? {}) as any;
  const orgId = requestOrgId(request, body);
  const ownerScope = ownerScopeForRequest(request, body);
  const value = body.model_ref;
  if (value == null) {
    getRuntime().store.setSetting(orgId, defaultRefSettingKey(ownerScope), "");
    return { model_ref: null };
  }
  if (typeof value !== "string") return badRequest(reply, "Invalid model_ref");
  const parsed = parseModelRef(value.trim());
  if (!parsed) return badRequest(reply, "Invalid model_ref");
  const provider = providerByKey(orgId, parsed.providerKey, ownerScope);
  const model = modelByKey(orgId, parsed.providerKey, parsed.modelKey, ownerScope);
  if (!provider || !provider.enabled) return badRequest(reply, "Default model provider is not available");
  if (!model || !model.enabled) return badRequest(reply, "Default model is not available");
  getRuntime().store.setSetting(
    orgId,
    defaultRefSettingKey(ownerScope),
    modelRef(parsed.providerKey, parsed.modelKey),
  );
  return { model_ref: modelRef(parsed.providerKey, parsed.modelKey) };
}

export function registerModelConfigRoutes(app: FastifyInstance): void {
  app.get("/api/model-providers", async (request) => listProviders(request));
  app.post("/api/model-providers", async (request, reply) => createProvider(request, reply));
  app.get("/api/model-providers/:provider_key", async (request, reply) => getProvider(request, reply));
  app.patch("/api/model-providers/:provider_key", async (request, reply) => updateProvider(request, reply));
  app.delete("/api/model-providers/:provider_key", async (request, reply) => deleteProvider(request, reply));

  app.get("/api/model-providers/:provider_key/models", async (request, reply) => listModels(request, reply));
  app.post("/api/model-providers/:provider_key/models", async (request, reply) => createModel(request, reply));
  app.get("/api/model-providers/:provider_key/models/:model_key", async (request, reply) => getModel(request, reply));
  app.patch("/api/model-providers/:provider_key/models/:model_key", async (request, reply) => updateModel(request, reply));
  app.delete("/api/model-providers/:provider_key/models/:model_key", async (request, reply) => deleteModel(request, reply));

  app.get("/api/model-default", async (request) => getDefaultModel(request));
  app.put("/api/model-default", async (request, reply) => setDefaultModel(request, reply));
}
