import type { BrandingPublicConfig } from "../types/config";

export const DEFAULT_THEME_COLORS = {
  primary: "#2563EB",
  secondary: "#1A1A1A",
  accent: "#3B82F6",
} as const;

/**
 * Validates hexadecimal color strings strictly (#RGB or #RRGGBB).
 * Prevents arbitrary injection into DOM styles.
 */
export function isValidHexColor(color?: string | null): boolean {
  if (!color || typeof color !== "string") {
    return false;
  }
  return /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(color.trim());
}

/**
 * Safely sanitizes a hex color, falling back to a known safe value if invalid.
 */
export function sanitizeColor(color: string | undefined | null, fallback: string): string {
  if (isValidHexColor(color)) {
    return color!.trim();
  }
  return fallback;
}

/**
 * Injects CSS custom properties into :root (document.documentElement).
 */
export function applyThemeTokens(branding?: Partial<BrandingPublicConfig> | null): void {
  if (typeof document === "undefined") {
    return;
  }

  const root = document.documentElement;

  const primary = sanitizeColor(branding?.primaryColor, DEFAULT_THEME_COLORS.primary);
  const secondary = sanitizeColor(branding?.secondaryColor, DEFAULT_THEME_COLORS.secondary);
  const accent = sanitizeColor(branding?.accentColor, DEFAULT_THEME_COLORS.accent);

  root.style.setProperty("--color-primary", primary);
  root.style.setProperty("--color-secondary", secondary);
  root.style.setProperty("--color-accent", accent);
}

/**
 * Updates document.title and favicon link tag dynamically.
 */
export function applyDocumentBranding(
  assistantName?: string,
  organizationName?: string,
  faviconUrl?: string
): void {
  if (typeof document === "undefined") {
    return;
  }

  // Set document.title
  if (assistantName && organizationName) {
    document.title = `${assistantName} | ${organizationName}`;
  } else if (assistantName) {
    document.title = assistantName;
  } else if (organizationName) {
    document.title = organizationName;
  }

  // Set favicon if provided and valid
  if (faviconUrl && typeof faviconUrl === "string") {
    let faviconLink = document.querySelector("link[rel*='icon']") as HTMLLinkElement | null;
    if (!faviconLink) {
      faviconLink = document.createElement("link");
      faviconLink.rel = "shortcut icon";
      document.head.appendChild(faviconLink);
    }
    faviconLink.href = faviconUrl;
  }
}
