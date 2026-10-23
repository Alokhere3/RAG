# White-Label Branding System Guide

The RAG platform is architected from the ground up as a reusable, white-label product. A single pre-built Docker image can be deployed across unlimited clients without code changes or client-specific rebuilds.

---

## 1. Multi-Client Deployment Model

```text
                    PRE-BUILT DOCKER IMAGES
                 (rag-frontend & rag-backend)
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
       Client Deployment A             Client Deployment B
      (e.g., Acme Corporation)        (e.g., Example University)
      ├── same Docker images          ├── same Docker images
      ├── client .env                 ├── client .env
      └── client branding             └── client branding
              │                               │
       Client .env:                    Client .env:
       ORGANIZATION_NAME=Acme          ORGANIZATION_NAME=Example Uni
       ASSISTANT_NAME=Acme Copilot     ASSISTANT_NAME=Uni Advisor
       PRIMARY_COLOR=#10B981           PRIMARY_COLOR=#7C3AED
              │                               │
              ▼                               ▼
       Independent UI                  Independent UI
       (Emerald Theme, Acme Logo)      (Purple Theme, Uni Logo)
```

### Deployment Rule: Zero Code Fork
- **No Source Modifications**: Branding is never hardcoded in TypeScript, JSX, or HTML.
- **No Client Rebuilds**: The frontend application does not require `npm run build` or image baking per tenant.
- **No Image Multiplicity**: CI builds a single `rag-frontend:latest` and `rag-backend:latest` pair. Different clients simply mount different `.env` files.

---

## 2. White-Label Capabilities

### A. Organization Identity
* **`ORGANIZATION_NAME`**: Displayed on application headers, footers, status indicators, and browser title bars.
* **`ORGANIZATION_LOGO_URL`**: High-resolution brand logo displayed in the header. Supports HTTPS URLs or absolute root paths.
* **`ORGANIZATION_WEBSITE_URL`**: Link target for organization logo and brand credentials.

### B. Virtual Assistant Persona
* **`ASSISTANT_NAME`**: Identity of the virtual assistant companion (e.g., "Acme Copilot", "University Advisor").
* **`ASSISTANT_DESCRIPTION`**: Persona purpose tagline (e.g., "Ask questions about organization policies and internal documentation").
* **`ASSISTANT_AVATAR_URL`**: Profile picture, avatar badge, or bot icon.

### C. Visual Theme & Design Tokens
* **`PRIMARY_COLOR`**: Main accent color (`--color-primary`) applied to buttons, active navigation, and key status highlights.
* **`SECONDARY_COLOR`**: Surface contrast color (`--color-secondary`) applied to cards, dark backgrounds, and headings.
* **`ACCENT_COLOR`**: Secondary accent (`--color-accent`) applied to hover states, tags, and borders.
* **`FAVICON_URL`**: Browser tab favicon dynamically injected at application runtime.

### D. Feature Entitlements (Flags)
* **`ENABLE_CHAT`**: Toggle visibility of the chat interaction module.
* **`ENABLE_DOCUMENTS`**: Toggle visibility of the document knowledge ingestion module.

---

## 3. How White-Labeling Works at Runtime

```text
1. Container Launch:
   Backend loads client .env into Pydantic Settings.
      ↓
2. Browser Boot:
   Frontend loads generic SPA bundle (rag-frontend).
      ↓
3. Config Fetch:
   ConfigProvider calls GET /api/v1/config.
      ↓
4. Loading Gate:
   Displays generic loading indicator (prevents flash of unbranded UI).
      ↓
5. Theme & Metadata Injection:
   applyThemeTokens() sets CSS variables (--color-primary, --color-secondary, --color-accent).
   applyDocumentBranding() updates document.title and favicon.
      ↓
6. Branded Render:
   Consumer components render fully customized identity via useAppConfig().
```

---

## 4. Color Validation & CSS Injection Defense

To prevent malicious or malformed environment values from compromising the DOM:
- All hex color inputs are strictly validated against:
  ```text
  ^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$
  ```
- Any value containing semicolons, URL expressions, script tags, or non-hex characters is rejected.
- If an invalid color is supplied, the theme engine automatically falls back to safe default palette tokens (`#2563EB`, `#1E293B`, `#3B82F6`) without breaking UI execution.

---

## 5. Security Boundary

White-labeling is strictly isolated from platform secrets:
- The public config schema (`PublicConfigResponse`) exposes only presentation metadata.
- Database credentials, cache keys, token signing secrets, and AI API keys are masked on the server and never returned to the frontend.
- Feature flags govern UI component visibility only, never replacing server-side authorization.
