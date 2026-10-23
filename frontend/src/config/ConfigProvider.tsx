import React, { createContext, useCallback, useEffect, useState } from "react";
import type { ConfigContextValue, PublicConfigResponse } from "../types/config";
import { apiClient } from "../services/api";
import { applyThemeTokens, applyDocumentBranding } from "../theme/utils";

export const ConfigContext = createContext<ConfigContextValue | null>(null);

export interface ConfigProviderProps {
  children: React.ReactNode;
  initialConfig?: PublicConfigResponse | null;
}

export const ConfigProvider: React.FC<ConfigProviderProps> = ({
  children,
  initialConfig = null,
}) => {
  const [config, setConfig] = useState<PublicConfigResponse | null>(initialConfig);
  const [isLoading, setIsLoading] = useState<boolean>(!initialConfig);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getConfig();
      setConfig(data);
    } catch {
      // Safe, generic user-facing message - strictly no stack traces or URLs
      setError("Unable to load application configuration. Please contact the administrator.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!initialConfig) {
      fetchConfig();
    }
  }, [fetchConfig, initialConfig]);

  useEffect(() => {
    if (config) {
      applyThemeTokens(config.branding);
      applyDocumentBranding(
        config.assistant?.name,
        config.organization?.name,
        config.branding?.faviconUrl
      );
    }
  }, [config]);

  if (isLoading) {
    return (
      <main className="app-main">
        <div className="status-container">
          <div className="status-card" data-testid="config-loading">
            <div className="loading-state">
              <p>Loading application configuration...</p>
            </div>
          </div>
        </div>
      </main>
    );
  }

  if (error || !config) {
    return (
      <main className="app-main">
        <div className="status-container">
          <div className="status-card" data-testid="config-error">
            <div className="error-banner">
              ⚠️ {error || "Unable to load application configuration. Please contact the administrator."}
            </div>
            <p className="loading-state" style={{ padding: "0.5rem 0" }}>
              Please contact the administrator.
            </p>
          </div>
        </div>
      </main>
    );
  }

  const contextValue: ConfigContextValue = {
    config,
    isLoading: false,
    error: null,
    reloadConfig: fetchConfig,
    application: config.application,
    organization: config.organization,
    assistant: config.assistant,
    branding: config.branding,
    features: config.features,
  };

  return (
    <ConfigContext.Provider value={contextValue}>
      {children}
    </ConfigContext.Provider>
  );
};
