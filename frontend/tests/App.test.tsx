import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "../src/App";
import { appConfig } from "../src/config";

describe("Frontend System Status Baseline (F001 - F010)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("Test F001: Application renders without crashing", () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(() => {})));
    render(<App />);
    expect(screen.getByText("System Status")).toBeInTheDocument();
  });

  it("Test F002: Organization name is rendered from configuration", () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(() => {})));
    render(<App />);
    expect(screen.getByTestId("org-name")).toHaveTextContent(
      appConfig.organizationName
    );
  });

  it("Test F003: Bot name is rendered from configuration", () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(() => {})));
    render(<App />);
    expect(screen.getByTestId("bot-name")).toHaveTextContent(appConfig.botName);
  });

  it("Test F004 & F005: Readiness API success renders connected and healthy states", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        json: async () => ({
          status: "ready",
          dependencies: {
            database: "ok",
            redis: "ok",
          },
        }),
      })
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("status-row-backend")).toHaveTextContent("Connected");
      expect(screen.getByTestId("status-row-database")).toHaveTextContent("Healthy");
      expect(screen.getByTestId("status-row-redis")).toHaveTextContent("Healthy");
    });
  });

  it("Test F006: Backend unavailable renders error state gracefully", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Failed to fetch")));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("status-row-backend")).toHaveTextContent("Unavailable");
      expect(screen.getByTestId("status-row-database")).toHaveTextContent("Unavailable");
      expect(screen.getByTestId("status-row-redis")).toHaveTextContent("Unavailable");
      expect(screen.getByTestId("error-banner")).toHaveTextContent("Failed to fetch");
    });
  });

  it("Test F007: Database unhealthy renders database failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 503,
        ok: false,
        json: async () => ({
          status: "not_ready",
          dependencies: {
            database: "unavailable",
            redis: "ok",
          },
        }),
      })
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("status-row-backend")).toHaveTextContent("Connected");
      expect(screen.getByTestId("status-row-database")).toHaveTextContent("Unavailable");
      expect(screen.getByTestId("status-row-redis")).toHaveTextContent("Healthy");
    });
  });

  it("Test F008: Redis unhealthy renders Redis failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 503,
        ok: false,
        json: async () => ({
          status: "not_ready",
          dependencies: {
            database: "ok",
            redis: "unavailable",
          },
        }),
      })
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("status-row-backend")).toHaveTextContent("Connected");
      expect(screen.getByTestId("status-row-database")).toHaveTextContent("Healthy");
      expect(screen.getByTestId("status-row-redis")).toHaveTextContent("Unavailable");
    });
  });

  it("Test F009: Loading state is displayed before API completion", () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(() => {})));
    render(<App />);
    expect(screen.getByTestId("loading-state")).toHaveTextContent(
      "Checking system status..."
    );
  });

  it("Test F010: No organization-specific hardcoded branding exists in UI source", async () => {
    const fs = await import("fs");
    const path = await import("path");

    const filesToCheck = [
      path.resolve(__dirname, "../src/App.tsx"),
      path.resolve(__dirname, "../src/pages/StatusPage.tsx"),
      path.resolve(__dirname, "../src/components/StatusIndicator.tsx"),
    ];

    const forbiddenStrings = [
      "ABC Corporation",
      "ABC AI",
      "Demo Company",
      "Acme Corp",
    ];

    for (const filePath of filesToCheck) {
      const content = fs.readFileSync(filePath, "utf-8");
      for (const forbidden of forbiddenStrings) {
        expect(content).not.toContain(forbidden);
      }
    }
  });
});
