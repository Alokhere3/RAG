import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { ConfigProvider, useAppConfig } from "../src/config";
import { apiClient } from "../src/services/api";
import type { PublicConfigResponse } from "../src/types/config";

const mockValidConfig: PublicConfigResponse = {
  application: {
    name: "Enterprise Knowledge Assistant",
    version: "2.1.0",
  },
  organization: {
    name: "Acme Holdings",
    logoUrl: "/static/acme-logo.svg",
    websiteUrl: "https://acme.example.com",
  },
  assistant: {
    name: "Acme Copilot",
    description: "Enterprise search and insights assistant",
    avatarUrl: "/static/acme-avatar.png",
  },
  branding: {
    primaryColor: "#0F172A",
    secondaryColor: "#334155",
    accentColor: "#38BDF8",
    faviconUrl: "/static/favicon.ico",
  },
  features: {
    chat: true,
    documents: true,
  },
};

// Test consumer component
const TestConsumer: React.FC = () => {
  const { organization, assistant, branding, features, application } = useAppConfig();
  return (
    <div data-testid="consumer-view">
      <h1 data-testid="consumer-org">{organization.name}</h1>
      <p data-testid="consumer-bot">{assistant.name}</p>
      <span data-testid="consumer-primary-color">{branding.primaryColor}</span>
      <span data-testid="consumer-feature-chat">{features.chat ? "chat-on" : "chat-off"}</span>
      <span data-testid="consumer-version">{application.version}</span>
    </div>
  );
};

describe("Frontend Runtime Configuration (Chunk 1.4 Tests)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("Test C001 & C002: Loading state displays while loading, then successful response renders consumer component", async () => {
    let resolveConfigPromise: (value: unknown) => void;
    const pendingPromise = new Promise((resolve) => {
      resolveConfigPromise = resolve;
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/config")) {
          return pendingPromise;
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      })
    );

    render(
      <ConfigProvider>
        <TestConsumer />
      </ConfigProvider>
    );

    // Initial state: loading barrier
    expect(screen.getByTestId("config-loading")).toBeInTheDocument();
    expect(
      screen.getByText("Loading application configuration...")
    ).toBeInTheDocument();
    expect(screen.queryByTestId("consumer-view")).not.toBeInTheDocument();

    // Resolve API fetch
    resolveConfigPromise!({
      ok: true,
      status: 200,
      json: async () => mockValidConfig,
    });

    // After resolution: consumer renders correctly with runtime data
    await waitFor(() => {
      expect(screen.queryByTestId("config-loading")).not.toBeInTheDocument();
      expect(screen.getByTestId("consumer-view")).toBeInTheDocument();
      expect(screen.getByTestId("consumer-org")).toHaveTextContent("Acme Holdings");
      expect(screen.getByTestId("consumer-bot")).toHaveTextContent("Acme Copilot");
      expect(screen.getByTestId("consumer-primary-color")).toHaveTextContent("#0F172A");
      expect(screen.getByTestId("consumer-feature-chat")).toHaveTextContent("chat-on");
      expect(screen.getByTestId("consumer-version")).toHaveTextContent("2.1.0");
    });
  });

  it("Test C003: API failure displays safe error message without exposing URLs or stack traces", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("Network connection to http://127.0.0.1:8000 failed"))
    );

    render(
      <ConfigProvider>
        <TestConsumer />
      </ConfigProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("config-error")).toBeInTheDocument();
      expect(screen.getByText(/Unable to load application configuration/i)).toBeInTheDocument();
      // Verify NO leakage of internal URLs or technical errors to user
      expect(screen.queryByText(/127.0.0.1/)).not.toBeInTheDocument();
      expect(screen.queryByText(/8000/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Network connection/)).not.toBeInTheDocument();
    });
  });

  it("Test C004: Malformed response triggers safe error boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ application: { name: "Broken" } }), // missing organization, assistant, branding, features
      })
    );

    render(
      <ConfigProvider>
        <TestConsumer />
      </ConfigProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("config-error")).toBeInTheDocument();
      expect(screen.getByText(/Unable to load application configuration/i)).toBeInTheDocument();
      expect(screen.queryByTestId("consumer-view")).not.toBeInTheDocument();
    });
  });

  it("Test C005: Missing optional fields are handled gracefully", async () => {
    const minimalConfig: PublicConfigResponse = {
      application: {
        name: "Minimal App",
        version: "1.0.0",
      },
      organization: {
        name: "Minimal Org",
      },
      assistant: {
        name: "Minimal Bot",
      },
      branding: {
        primaryColor: "#000000",
        secondaryColor: "#111111",
        accentColor: "#222222",
      },
      features: {
        chat: false,
        documents: false,
      },
    };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => minimalConfig,
      })
    );

    render(
      <ConfigProvider>
        <TestConsumer />
      </ConfigProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("consumer-org")).toHaveTextContent("Minimal Org");
      expect(screen.getByTestId("consumer-bot")).toHaveTextContent("Minimal Bot");
      expect(screen.getByTestId("consumer-feature-chat")).toHaveTextContent("chat-off");
    });
  });

  it("Test C006: Consumer component rendering outside ConfigProvider falls back gracefully", () => {
    render(<TestConsumer />);
    expect(screen.getByTestId("consumer-view")).toBeInTheDocument();
    expect(screen.getByTestId("consumer-org")).toBeInTheDocument();
    expect(screen.getByTestId("consumer-bot")).toBeInTheDocument();
  });

  it("Test C007: ApiClient.getConfig makes correct request", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockValidConfig,
    });
    vi.stubGlobal("fetch", fetchMock);

    const config = await apiClient.getConfig();
    expect(config.application.name).toBe("Enterprise Knowledge Assistant");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/config"),
      expect.objectContaining({
        method: "GET",
        headers: { Accept: "application/json" },
      })
    );
  });

  it("Test C008: ConfigProvider renders immediately when initialConfig is provided", () => {
    render(
      <ConfigProvider initialConfig={mockValidConfig}>
        <TestConsumer />
      </ConfigProvider>
    );

    expect(screen.queryByTestId("config-loading")).not.toBeInTheDocument();
    expect(screen.getByTestId("consumer-org")).toHaveTextContent("Acme Holdings");
  });
});
