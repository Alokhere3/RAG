import { useAppConfig } from "../config";
import type { FeatureFlagName } from "./types";
import type { FeaturesPublicConfig } from "../types/config";

/**
 * Returns whether a feature flag is enabled.
 * Safely handles unknown or undefined feature flags by returning false.
 */
export function useFeatureFlag(name: FeatureFlagName): boolean {
  const { features } = useAppConfig();
  if (!features || typeof features !== "object") {
    return false;
  }
  const featureMap = features as unknown as Record<string, unknown>;
  const value = featureMap[name];
  return Boolean(value);
}

/**
 * Returns all active feature flags.
 */
export function useFeatureFlags(): FeaturesPublicConfig {
  const { features } = useAppConfig();
  return features;
}
