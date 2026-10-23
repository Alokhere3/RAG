import type { PublicConfigResponse, ConfigContextValue } from "../types/config";

export interface AppConfig {
  organizationName: string;
  botName: string;
  logoUrl: string;
  primaryColor: string;
  apiBaseUrl: string;
}

export const appConfig: AppConfig = {
  organizationName:
    (typeof import.meta !== "undefined" && import.meta.env?.VITE_ORGANIZATION_NAME) ||
    "Demo Organization",
  botName:
    (typeof import.meta !== "undefined" && import.meta.env?.VITE_BOT_NAME) ||
    "AI Assistant",
  logoUrl:
    (typeof import.meta !== "undefined" && import.meta.env?.VITE_LOGO_URL) || "",
  primaryColor:
    (typeof import.meta !== "undefined" && import.meta.env?.VITE_PRIMARY_COLOR) ||
    "#2563EB",
  apiBaseUrl:
    (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE_URL) || "",
};

export const defaultPublicConfig: PublicConfigResponse = {
  application: {
    name: "Knowledge Assistant",
    version: "1.0.0",
  },
  organization: {
    name: appConfig.organizationName,
    logoUrl: appConfig.logoUrl,
    websiteUrl: "",
  },
  assistant: {
    name: appConfig.botName,
    description: "Ask questions about your organization's knowledge.",
    avatarUrl: "",
  },
  branding: {
    primaryColor: appConfig.primaryColor,
    secondaryColor: "#1A1A1A",
    accentColor: "#D4AF37",
    faviconUrl: "",
  },
  features: {
    chat: false,
    documents: false,
  },
};

export const fallbackContextValue: ConfigContextValue = {
  config: defaultPublicConfig,
  isLoading: false,
  error: null,
  reloadConfig: async () => {},
  application: defaultPublicConfig.application,
  organization: defaultPublicConfig.organization,
  assistant: defaultPublicConfig.assistant,
  branding: defaultPublicConfig.branding,
  features: defaultPublicConfig.features,
};
