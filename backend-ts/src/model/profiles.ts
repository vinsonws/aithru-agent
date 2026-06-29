export interface AgentModelProfile {
  key: string;
  provider: string;
  model: string;
  enabled: boolean;
  required_scopes: string[];
  capabilities: string[];
  token_ceiling?: number;
}

export interface ModelProfileSelection {
  key: string;
  requested_capabilities?: string[];
  run_scopes: string[];
}

export class ModelProfileRegistry {
  private profiles = new Map<string, AgentModelProfile>();

  register(profile: AgentModelProfile): void {
    this.profiles.set(profile.key, profile);
  }

  get(key: string): AgentModelProfile | undefined {
    return this.profiles.get(key);
  }

  resolve(selection: ModelProfileSelection): AgentModelProfile {
    const profile = this.profiles.get(selection.key);
    if (!profile) throw new Error(`MODEL_PROFILE_NOT_FOUND: ${selection.key}`);
    if (!profile.enabled) throw new Error(`MODEL_PROFILE_DISABLED: ${selection.key}`);

    const scopes = new Set(selection.run_scopes);
    if (!scopes.has("*")) {
      const missing = profile.required_scopes.filter((scope) => !scopes.has(scope));
      if (missing.length > 0) {
        throw new Error(`MODEL_PROFILE_SCOPE_DENIED: ${missing.join(", ")}`);
      }
    }

    const requested = selection.requested_capabilities ?? [];
    const missingCapabilities = requested.filter(
      (capability) => !profile.capabilities.includes(capability),
    );
    if (missingCapabilities.length > 0) {
      throw new Error(
        `MODEL_PROFILE_CAPABILITY_DENIED: ${missingCapabilities.join(", ")}`,
      );
    }

    return profile;
  }
}
