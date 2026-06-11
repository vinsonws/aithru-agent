import type {
  AithruPlatform,
  AithruPlatformConfig,
} from "@aithru/subsystem-sdk-node";
import type { PlatformConfig } from "./config.js";

/**
 * Create an AithruPlatform facade for the Agent subsystem.
 *
 * Maps Agent PlatformConfig to SDK config shape.
 */
export function createAgentAithruPlatform(
  cfg: PlatformConfig,
): Promise<AithruPlatform> {
  const sdkConfig: Partial<AithruPlatformConfig> = {
    baseUrl: cfg.platformUrl,
    issuer: cfg.issuer,
    appKey: cfg.appKey,
    serviceName: cfg.serviceName,
    serviceVersion: cfg.serviceVersion,
    clientId: cfg.clientId,
    clientSecret: cfg.clientSecret,
    audience: cfg.audience,
    publicBaseUrl: cfg.publicBaseUrl,
    internalBaseUrl: cfg.internalBaseUrl,
    healthUrl: cfg.healthUrl,
    manifestLocation: cfg.manifestLocation,
    registrationEnabled: cfg.registrationEnabled,
    failOnRegistrationError: cfg.failOnRegistrationError,
  };

  return createOptionalAithruPlatform(sdkConfig);
}

async function createOptionalAithruPlatform(
  sdkConfig: Partial<AithruPlatformConfig>,
): Promise<AithruPlatform> {
  const { createAithruPlatform } = await import(
    "@aithru/subsystem-sdk-node"
  ).catch((cause: unknown) => {
    throw new Error(
      "Platform subsystem mode requires optional dependency @aithru/subsystem-sdk-node. Install it from Nexus or link it locally before running dev:platform.",
      { cause },
    );
  });

  return createAithruPlatform(sdkConfig);
}
