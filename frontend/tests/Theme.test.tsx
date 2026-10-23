import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ConfigProvider } from "../src/config";
import { StatusPage } from "../src/pages/StatusPage";
import {
  isValidHexColor,
  sanitizeColor,
  applyThemeTokens,
  applyDocumentBranding,
  DEFAULT_THEME_COLORS,
} from "../src/theme/utils";
import type { PublicConfigResponse } from "../src/types/config";

describe("White-Label Theme & Branding (Chunk 1.5 Tests)", () => {
  const originalTitle = document.title;

  beforeEach(() => {
    vi.restoreAllMocks();
    document.title = originalTitle;
    document.documentElement.style.removeProperty("--color-primary");
    document.documentElement.style.removeProperty("--color-secondary");
    document.documentElement.style.removeProperty("--color-accent");
    const existingIcon = document.querySelector("link[rel*='icon']");
    if (existingIcon) {
      existingIcon.remove();
    }
  });

  afterEach(() => {
    document.title = originalTitle;
  });

  it("Test T001: isValidHexColor validates hex colors strictly and rejects injection attempts", () => {
    // Valid formats
    expect(isValidHexColor("#fff")).toBe(true);
    expect(isValidHexColor("#FFFFFF")).toBe(true);
    expect(isValidHexColor("#2563EB")).toBe(true);
    expect(isValidHexColor("#1a1a1a")).toBe(true);

    // Invalid formats & CSS injection attempts
    expect(isValidHexColor("")).toBe(false);
    expect(isValidHexColor("blue")).toBe(false);
    expect(isValidHexColor("#12345")).toBe(false);
    expect(isValidHexColor("#1234567")).toBe(false);
    expect(isValidHexColor("rgb(0,0,0)")).toBe(false);
    expect(isValidHexColor("#2563EB; background: url('evil.png')")).toBe(false);
    expect(isValidHexColor("<script>alert(1)</script>")).toBe(false);
    expect(isValidHexColor(null)).toBe(false);
    expect(isValidHexColor(undefined)).toBe(false);
  });

  it("Test T002: sanitizeColor uses valid color or falls back to safe default", () => {
    expect(sanitizeColor("#FF5733", "#000000")).toBe("#FF5733");
    expect(sanitizeColor("invalid-color", "#000000")).toBe("#000000");
    expect(sanitizeColor(undefined, "#000000")).toBe("#000000");
  });

  it("Test T003: applyThemeTokens sets CSS custom properties on document.documentElement", () => {
    applyThemeTokens({
      primaryColor: "#FF0000",
      secondaryColor: "#00FF00",
      accentColor: "#0000FF",
      faviconUrl: "",
    });

    expect(
      document.documentElement.style.getPropertyValue("--color-primary")
    ).toBe("#FF0000");
    expect(
      document.documentElement.style.getPropertyValue("--color-secondary")
    ).toBe("#00FF00");
    expect(
      document.documentElement.style.getPropertyValue("--color-accent")
    ).toBe("#0000FF");
  });

  it("Test T004: applyThemeTokens safely falls back when given malicious or invalid color values", () => {
    applyThemeTokens({
      primaryColor: "not-a-color; evil-css",
      secondaryColor: "",
      accentColor: "#GGGGGG",
      faviconUrl: "",
    });

    expect(
      document.documentElement.style.getPropertyValue("--color-primary")
    ).toBe(DEFAULT_THEME_COLORS.primary);
    expect(
      document.documentElement.style.getPropertyValue("--color-secondary")
    ).toBe(DEFAULT_THEME_COLORS.secondary);
    expect(
      document.documentElement.style.getPropertyValue("--color-accent")
    ).toBe(DEFAULT_THEME_COLORS.accent);
  });

  it("Test T005: applyDocumentBranding updates document.title and favicon", () => {
    applyDocumentBranding(
      "Enterprise Assistant",
      "Globex Corp",
      "https://example.com/custom-favicon.ico"
    );

    expect(document.title).toBe("Enterprise Assistant | Globex Corp");
    const icon = document.querySelector("link[rel*='icon']") as HTMLLinkElement;
    expect(icon).not.toBeNull();
    expect(icon.href).toBe("https://example.com/custom-favicon.ico");
  });

  it("Test T006: White-label changes reflect dynamically in UI via ConfigProvider", async () => {
    const brandedConfig: PublicConfigResponse = {
      application: {
        name: "Enterprise Platform",
        version: "3.0.0",
      },
      organization: {
        name: "Stark Industries",
        logoUrl: "https://example.com/stark-logo.png",
        websiteUrl: "https://stark.example.com",
      },
      assistant: {
        name: "J.A.R.V.I.S.",
        description: "Just A Rather Very Intelligent System",
        avatarUrl: "https://example.com/jarvis-avatar.png",
      },
      branding: {
        primaryColor: "#A30000",
        secondaryColor: "#111111",
        accentColor: "#FFD700",
        faviconUrl: "https://example.com/stark.ico",
      },
      features: {
        chat: true,
        documents: true,
      },
    };

    // Mock readiness fetch for StatusPage
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/health/ready")) {
          return Promise.resolve({
            status: 200,
            ok: true,
            json: async () => ({
              status: "ready",
              dependencies: { database: "ok", redis: "ok" },
            }),
          });
        }
        return Promise.resolve({
          status: 200,
          ok: true,
          json: async () => brandedConfig,
        });
      })
    );

    render(
      <ConfigProvider initialConfig={brandedConfig}>
        <StatusPage />
      </ConfigProvider>
    );

    // Verify Organization name changes
    expect(screen.getByTestId("org-name")).toHaveTextContent("Stark Industries");

    // Verify Assistant name changes
    expect(screen.getByTestId("bot-name")).toHaveTextContent("J.A.R.V.I.S.");

    // Verify Logo changes
    const logoImg = screen.getByAltText("Stark Industries Logo");
    expect(logoImg).toBeInTheDocument();
    expect(logoImg).toHaveAttribute("src", "https://example.com/stark-logo.png");

    // Verify CSS tokens applied to :root
    await waitFor(() => {
      expect(
        document.documentElement.style.getPropertyValue("--color-primary")
      ).toBe("#A30000");
      expect(
        document.documentElement.style.getPropertyValue("--color-secondary")
      ).toBe("#111111");
      expect(
        document.documentElement.style.getPropertyValue("--color-accent")
      ).toBe("#FFD700");
    });

    // Verify Page title changes
    expect(document.title).toBe("J.A.R.V.I.S. | Stark Industries");

    // Verify Favicon changes
    const icon = document.querySelector("link[rel*='icon']") as HTMLLinkElement;
    expect(icon).not.toBeNull();
    expect(icon.href).toBe("https://example.com/stark.ico");
  });
});
