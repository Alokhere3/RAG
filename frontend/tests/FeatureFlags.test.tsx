import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConfigProvider } from "../src/config";
import { FeatureGate, useFeatureFlag, useFeatureFlags } from "../src/features";
import { StatusPage } from "../src/pages/StatusPage";
import type { PublicConfigResponse } from "../src/types/config";

const baseConfig: PublicConfigResponse = {
  application: { name: "App", version: "1.0.0" },
  organization: { name: "Org" },
  assistant: { name: "Bot" },
  branding: { primaryColor: "#000", secondaryColor: "#111", accentColor: "#222" },
  features: { chat: false, documents: false },
};

// Component to test hook behavior
const FeatureInspector: React.FC<{ flagName: string }> = ({ flagName }) => {
  const isEnabled = useFeatureFlag(flagName);
  const allFlags = useFeatureFlags();

  return (
    <div>
      <span data-testid="flag-state">{isEnabled ? "ENABLED" : "DISABLED"}</span>
      <span data-testid="chat-flag-prop">{String(allFlags.chat)}</span>
      <span data-testid="docs-flag-prop">{String(allFlags.documents)}</span>
    </div>
  );
};

describe("Feature Flag Foundation (Chunk 1.6 Tests)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("Test FF001: Feature enabled → visible using FeatureGate and useFeatureFlag", () => {
    const configWithChat: PublicConfigResponse = {
      ...baseConfig,
      features: { chat: true, documents: false },
    };

    render(
      <ConfigProvider initialConfig={configWithChat}>
        <FeatureGate feature="chat" fallback={<span data-testid="fallback">Fallback</span>}>
          <div data-testid="chat-content">Chat Component Active</div>
        </FeatureGate>
        <FeatureInspector flagName="chat" />
      </ConfigProvider>
    );

    // Visible because feature is enabled
    expect(screen.getByTestId("chat-content")).toBeInTheDocument();
    expect(screen.getByText("Chat Component Active")).toBeInTheDocument();
    expect(screen.queryByTestId("fallback")).not.toBeInTheDocument();
    expect(screen.getByTestId("flag-state")).toHaveTextContent("ENABLED");
    expect(screen.getByTestId("chat-flag-prop")).toHaveTextContent("true");
  });

  it("Test FF002: Feature disabled → hidden and fallback rendered", () => {
    const configNoChat: PublicConfigResponse = {
      ...baseConfig,
      features: { chat: false, documents: false },
    };

    render(
      <ConfigProvider initialConfig={configNoChat}>
        <FeatureGate feature="chat" fallback={<span data-testid="chat-fallback">Chat Unavailable</span>}>
          <div data-testid="chat-content">Chat Component Active</div>
        </FeatureGate>
        <FeatureInspector flagName="chat" />
      </ConfigProvider>
    );

    // Hidden because feature is disabled
    expect(screen.queryByTestId("chat-content")).not.toBeInTheDocument();
    expect(screen.getByTestId("chat-fallback")).toHaveTextContent("Chat Unavailable");
    expect(screen.getByTestId("flag-state")).toHaveTextContent("DISABLED");
  });

  it("Test FF003: Unknown feature is safely ignored (returns false and renders fallback)", () => {
    render(
      <ConfigProvider initialConfig={baseConfig}>
        <FeatureGate feature="quantum_neural_engine" fallback={<span data-testid="unknown-fallback">None</span>}>
          <div data-testid="unknown-content">Should Not Render</div>
        </FeatureGate>
        <FeatureInspector flagName="quantum_neural_engine" />
      </ConfigProvider>
    );

    expect(screen.queryByTestId("unknown-content")).not.toBeInTheDocument();
    expect(screen.getByTestId("unknown-fallback")).toHaveTextContent("None");
    expect(screen.getByTestId("flag-state")).toHaveTextContent("DISABLED");
  });

  it("Test FF004: StatusPage conditionally renders chat and documents feature badges when flags are enabled", async () => {
    // Health probe mock for StatusPage
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve({
          status: 200,
          ok: true,
          json: async () => ({
            status: "ready",
            dependencies: { database: "ok", redis: "ok" },
          }),
        })
      )
    );

    const configBothFeatures: PublicConfigResponse = {
      ...baseConfig,
      features: { chat: true, documents: true },
    };

    render(
      <ConfigProvider initialConfig={configBothFeatures}>
        <StatusPage />
      </ConfigProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("feature-chat-badge")).toHaveTextContent("💬 Chat Module Enabled");
      expect(screen.getByTestId("feature-documents-badge")).toHaveTextContent("📄 Documents Module Enabled");
    });
  });

  it("Test FF005: StatusPage hides feature badges when flags are disabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve({
          status: 200,
          ok: true,
          json: async () => ({
            status: "ready",
            dependencies: { database: "ok", redis: "ok" },
          }),
        })
      )
    );

    const configNoFeatures: PublicConfigResponse = {
      ...baseConfig,
      features: { chat: false, documents: false },
    };

    render(
      <ConfigProvider initialConfig={configNoFeatures}>
        <StatusPage />
      </ConfigProvider>
    );

    await waitFor(() => {
      expect(screen.queryByTestId("feature-chat-badge")).not.toBeInTheDocument();
      expect(screen.queryByTestId("feature-documents-badge")).not.toBeInTheDocument();
    });
  });
});
