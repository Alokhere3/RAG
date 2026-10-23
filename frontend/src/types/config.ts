/**
 * Strongly typed contracts for runtime application configuration.
 * Maps 1:1 with backend PublicConfigResponse schema.
 */

export interface ApplicationPublicConfig {
  name: string;
  version: string;
}

export interface OrganizationPublicConfig {
  name: string;
  logoUrl?: string;
  websiteUrl?: string;
}

export interface AssistantPublicConfig {
  name: string;
  description?: string;
  avatarUrl?: string;
}

export interface BrandingPublicConfig {
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  faviconUrl?: string;
}

export interface FeaturesPublicConfig {
  chat: boolean;
  documents: boolean;
}

export interface PublicConfigResponse {
  application: ApplicationPublicConfig;
  organization: OrganizationPublicConfig;
  assistant: AssistantPublicConfig;
  branding: BrandingPublicConfig;
  features: FeaturesPublicConfig;
}

export interface ConfigContextValue {
  config: PublicConfigResponse;
  isLoading: boolean;
  error: string | null;
  reloadConfig: () => Promise<void>;
  // Direct shortcuts for ergonomic consumption
  application: ApplicationPublicConfig;
  organization: OrganizationPublicConfig;
  assistant: AssistantPublicConfig;
  branding: BrandingPublicConfig;
  features: FeaturesPublicConfig;
}
