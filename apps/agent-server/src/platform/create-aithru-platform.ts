import { createAithruPlatform } from "@aithru/subsystem-sdk-node";
import type { AithruPlatformConfig } from "@aithru/subsystem-sdk-node";
import type { PlatformConfig } from "./config.js";

/**
 * Create an AithruPlatform facade for the Agent subsystem.
 *
 * Maps Agent PlatformConfig to SDK config shape.
 */
export function createAgentAithruPlatform(
  cfg: PlatformConfig,
): ReturnType<typeof createAithruPlatform> {
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

  return createAithruPlatform(sdkConfig);
}
