export type PlatformConfig = {
  port: number;
  /** Five required production environment variables */
  platformUrl: string;
  appKey: string;
  clientSecret: string;
  publicBaseUrl: string;
  internalBaseUrl: string;
  /** Convention-derived (with optional overrides) */
  issuer: string;
  audience: string;
  clientId: string;
  serviceName: string;
  healthUrl: string;
  /** Optional controls */
  serviceVersion: string;
  manifestLocation: string;
  registrationEnabled: boolean;
  failOnRegistrationError: boolean;
};

function env(name: string, fallback: string): string {
  return process.env[name] ?? fallback;
}

function envBool(name: string, fallback: boolean): boolean {
  const v = process.env[name];
  if (v === undefined) return fallback;
  return v === "true" || v === "1" || v === "yes";
}

export function loadPlatformConfig(): PlatformConfig {
  const port = parseInt(env("PORT", env("AITHRU_AGENT_SERVER_PORT", "4317")), 10);

  const platformUrl = env("AITHRU_PLATFORM_URL", "http://localhost:8080");
  const appKey = env("AITHRU_APP_KEY", "agent");
  const publicBaseUrl = env("AITHRU_PUBLIC_BASE_URL", `http://localhost:${port}`);
  const internalBaseUrl = env("AITHRU_INTERNAL_BASE_URL", `http://localhost:${port}`);

  return {
    port,
    platformUrl,
    appKey,
    clientSecret: env("AITHRU_CLIENT_SECRET", "agent-secret"),
    publicBaseUrl,
    internalBaseUrl,

    // Convention-derived with optional overrides
    issuer: env("AITHRU_ISSUER", platformUrl),
    audience: env("AITHRU_AUDIENCE", appKey),
    clientId: env("AITHRU_CLIENT_ID", `${appKey}-client`),
    serviceName: env("AITHRU_SERVICE_NAME", `${appKey}-api`),
    healthUrl: env("AITHRU_HEALTH_URL", `${internalBaseUrl}/health`),

    // Optional controls
    serviceVersion: env("AITHRU_SERVICE_VERSION", "0.2.0-alpha.0"),
    manifestLocation: env("AITHRU_MANIFEST_LOCATION", "apps/agent-server/aithru-app.yml"),
    registrationEnabled: envBool("AITHRU_REGISTRATION_ENABLED", true),
    failOnRegistrationError: envBool("AITHRU_FAIL_ON_REGISTRATION_ERROR", true),
  };
}
