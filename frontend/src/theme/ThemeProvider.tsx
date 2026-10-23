import React, { useEffect } from "react";
import { useAppConfig } from "../config";
import { applyThemeTokens, applyDocumentBranding } from "./utils";
import type {
  BrandingPublicConfig,
  AssistantPublicConfig,
  OrganizationPublicConfig,
} from "../types/config";

export interface ThemeProviderProps {
  children: React.ReactNode;
  customBranding?: Partial<BrandingPublicConfig>;
  customAssistant?: Partial<AssistantPublicConfig>;
  customOrganization?: Partial<OrganizationPublicConfig>;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({
  children,
  customBranding,
  customAssistant,
  customOrganization,
}) => {
  const { branding, assistant, organization } = useAppConfig();

  const effectiveBranding = customBranding || branding;
  const effectiveAssistant = customAssistant || assistant;
  const effectiveOrganization = customOrganization || organization;

  useEffect(() => {
    applyThemeTokens(effectiveBranding);
    applyDocumentBranding(
      effectiveAssistant?.name,
      effectiveOrganization?.name,
      effectiveBranding?.faviconUrl
    );
  }, [effectiveBranding, effectiveAssistant, effectiveOrganization]);

  return <>{children}</>;
};
