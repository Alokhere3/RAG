/**
 * Feature flag identifiers.
 * Includes known flags while allowing arbitrary strings for runtime safety.
 */
export type FeatureFlagName = "chat" | "documents" | (string & {});
