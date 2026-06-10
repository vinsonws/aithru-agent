export type PlatformConfig = {
  port: number;
  platformUrl: string;
  issuer: string;
  appKey: string;
  serviceName: string;
  serviceVersion: string;
  clientId: string;
  clientSecret: string;
  audience: string;
  publicBaseUrl: string;
  internalBaseUrl: string;
  healthUrl: string;
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

  return {
    port,
    platformUrl: env("AITHRU_PLATFORM_URL", "http://localhost:8080"),
    issuer: env("AITHRU_ISSUER", "http://localhost:8080"),
    appKey: env("AITHRU_APP_KEY", "agent"),
    serviceName: env("AITHRU_SERVICE_NAME", "agent-api"),
    serviceVersion: env("AITHRU_SERVICE_VERSION", "0.2.0-alpha.0"),
    clientId: env("AITHRU_CLIENT_ID", "agent-client"),
    clientSecret: env("AITHRU_CLIENT_SECRET", "agent-secret"),
    audience: env("AITHRU_AUDIENCE", "agent"),
    publicBaseUrl: env("AITHRU_PUBLIC_BASE_URL", `http://localhost:${port}`),
    internalBaseUrl: env("AITHRU_INTERNAL_BASE_URL", `http://localhost:${port}`),
    healthUrl: env("AITHRU_HEALTH_URL", `http://localhost:${port}/health`),
    manifestLocation: env("AITHRU_MANIFEST_LOCATION", "apps/agent-server/aithru-app.yml"),
    registrationEnabled: envBool("AITHRU_REGISTRATION_ENABLED", true),
    failOnRegistrationError: envBool("AITHRU_FAIL_ON_REGISTRATION_ERROR", false),
  };
}
