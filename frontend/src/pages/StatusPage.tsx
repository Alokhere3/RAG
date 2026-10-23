import React from "react";
import { useAppConfig } from "../config";
import { useHealth } from "../hooks/useHealth";
import { StatusIndicator } from "../components/StatusIndicator";
import { FeatureGate } from "../features";

export const StatusPage: React.FC = () => {
  const { organization, assistant } = useAppConfig();
  const { status, refresh } = useHealth(10000); // Poll every 10s

  return (
    <div className="status-container">
      <div className="status-card">
        <header className="brand-header">
          {organization.logoUrl ? (
            <img
              src={organization.logoUrl}
              alt={`${organization.name} Logo`}
              className="brand-logo"
            />
          ) : (
            <div className="logo-placeholder" aria-label="Brand Icon">
              <svg
                width="36"
                height="36"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
            </div>
          )}

          <h1 className="organization-name" data-testid="org-name">
            {organization.name}
          </h1>
          <p className="bot-name" data-testid="bot-name">
            {assistant.name}
          </p>
        </header>

        <section className="status-section" aria-label="System Status">
          <h2 className="section-title">System Status</h2>

          {status.isLoading ? (
            <div className="loading-state" data-testid="loading-state">
              Checking system status...
            </div>
          ) : (
            <div className="status-list">
              <StatusIndicator
                label="Backend"
                status={status.backend}
                healthyLabel="Connected"
              />
              <StatusIndicator
                label="Database"
                status={status.database}
                healthyLabel="Healthy"
              />
              <StatusIndicator
                label="Redis"
                status={status.redis}
                healthyLabel="Healthy"
              />
            </div>
          )}

          {status.error && (
            <div className="error-banner" data-testid="error-banner">
              ⚠️ {status.error}
            </div>
          )}

          <div className="features-container" data-testid="features-container">
            <FeatureGate feature="chat">
              <div className="feature-badge" data-testid="feature-chat-badge">
                💬 Chat Module Enabled
              </div>
            </FeatureGate>
            <FeatureGate feature="documents">
              <div className="feature-badge" data-testid="feature-documents-badge">
                📄 Documents Module Enabled
              </div>
            </FeatureGate>
          </div>

          <footer className="status-footer">
            {status.lastChecked && (
              <span className="last-checked">
                Last checked: {status.lastChecked}
              </span>
            )}
            <button
              onClick={() => refresh()}
              className="refresh-button"
              disabled={status.isLoading}
            >
              Refresh Status
            </button>
          </footer>
        </section>
      </div>
    </div>
  );
};
