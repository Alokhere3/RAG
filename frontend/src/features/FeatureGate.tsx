import React from "react";
import { useFeatureFlag } from "./useFeatureFlag";
import type { FeatureFlagName } from "./types";

export interface FeatureGateProps {
  feature: FeatureFlagName;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Declaratively renders children if a feature flag is enabled,
 * or optional fallback if disabled.
 */
export const FeatureGate: React.FC<FeatureGateProps> = ({
  feature,
  children,
  fallback = null,
}) => {
  const isEnabled = useFeatureFlag(feature);
  if (isEnabled) {
    return <>{children}</>;
  }
  return <>{fallback}</>;
};
