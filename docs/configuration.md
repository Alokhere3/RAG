# Configuration System Architecture & Reference

The RAG platform employs a 3-layer configuration model providing strict isolation between private server secrets, public application settings, and client runtime state.

---

## 1. Architectural Layers

```text
┌─────────────────────────────────────────────────────────────┐
│ Layer A — Private Server Infrastructure                     │
│ DATABASE_URL, REDIS_URL, JWT_SECRET, LLM Keys               │
│ • Loaded via Pydantic Settings                              │
│ • Strongly masked in logs and memory (SecretString)         │
│ • Never exposed to clients or web browsers                  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer B — Public Application Configuration                  │
│ Organization, Assistant, Theme Tokens, Feature Flags         │
│ • Explicitly mapped via PublicConfigResponse Pydantic model │
│ • Validated hex color tokens & sanitized URLs               │
│ • Exposed over HTTP via GET /api/v1/config                  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer C — Frontend Runtime State                            │
│ React ConfigProvider -> useAppConfig -> CSS Custom Props    │
│ • Dynamically loaded at application boot                    │
│ • Eliminates build-time client bundling                     │
│ • Powers instant client rebranding without rebuilding       │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Configuration Reference

| Property | Example / Value |
|---|---|
| **Name** | Environment variable identifier |
| **Type** | Data type (`string`, `integer`, `boolean`, `enum`, `url`, `hex_color`) |
| **Required** | `Yes` (mandatory) or `No` (has defaults or optional) |
| **Secret** | `Yes` (masked, private to server) or `No` |
| **Public** | `Yes` (exposed via `/api/v1/config`) or `No` |
| **Default** | Default value when unspecified |
| **Description** | Operational purpose and behavior |
| **Production requirement** | Validation rules enforced when `APP_ENV=production` |

---

### Application & Runtime Environment

| Name | Type | Required | Secret | Public | Default | Description | Production requirement |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| `APP_ENV` | enum | No | No | Yes | `development` | Runtime environment (`development`, `testing`, `staging`, `production`) | Must be set to `production` |
| `APP_NAME` | string | No | No | Yes | `RAG Platform` | Public platform title and system banner | Any non-empty string |
| `APP_VERSION` | string | No | No | Yes | `0.1.0` | Application release version string | Semantic version recommended |
| `DEBUG` | boolean | No | No | No | `false` | Enables verbose tracebacks and reloaders | **Must be `false`** (strictly rejected if true) |
| `API_V1_PREFIX` | string | No | No | No | `/api/v1` | URL path namespace prefix for v1 API endpoints | Must start with `/` |
| `BACKEND_PORT` | integer | No | No | No | `8001` | Host port mapped to backend Uvicorn server | Valid port number (1024-65535) |
| `FRONTEND_PORT` | integer | No | No | No | `3001` | Host port mapped to frontend Nginx server | Valid port number (1024-65535) |
| `HOST` | string | No | No | No | `0.0.0.0` | Network binding interface address | `0.0.0.0` inside container |
| `CORS_ORIGINS` | string | No | No | No | `http://localhost:3000,http://localhost:3001` | Comma-separated allowed HTTP origins | **Wildcard `*` is strictly forbidden** |

---

### Organization White-Label Branding

| Name | Type | Required | Secret | Public | Default | Description | Production requirement |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| `ORGANIZATION_NAME` | string | No | No | Yes | `Demo Organization` | Client company/institution display name | Set to client legal/brand name |
| `ORGANIZATION_LOGO_URL` | url | No | No | Yes | `""` | URL to organization brand logo image | Valid HTTP/HTTPS or absolute path `/` |
| `ORGANIZATION_WEBSITE_URL` | url | No | No | Yes | `""` | URL to organization corporate website | Valid HTTP/HTTPS or absolute path `/` |

---

### Assistant Persona

| Name | Type | Required | Secret | Public | Default | Description | Production requirement |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| `ASSISTANT_NAME` | string | No | No | Yes | `AI Assistant` | Display name of the virtual assistant companion | Client assistant persona name |
| `ASSISTANT_DESCRIPTION` | string | No | No | Yes | `Ask questions...` | Introductory tagline explaining persona scope | User-facing descriptive tagline |
| `ASSISTANT_AVATAR_URL` | url | No | No | Yes | `""` | URL to assistant avatar picture or icon | Valid HTTP/HTTPS or absolute path `/` |

---

### Visual Theme & Design Tokens

| Name | Type | Required | Secret | Public | Default | Description | Production requirement |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| `PRIMARY_COLOR` | hex_color | No | No | Yes | `#2563EB` | Primary brand accent color for action buttons | Must match `#RGB` or `#RRGGBB` hex pattern |
| `SECONDARY_COLOR` | hex_color | No | No | Yes | `#1E293B` | Surface and dark element contrast color | Must match `#RGB` or `#RRGGBB` hex pattern |
| `ACCENT_COLOR` | hex_color | No | No | Yes | `#3B82F6` | Highlights, badges, and focus indicator color | Must match `#RGB` or `#RRGGBB` hex pattern |
| `FAVICON_URL` | url | No | No | Yes | `""` | Custom browser tab favicon URL | Valid HTTP/HTTPS or absolute path `/` |

---

### Feature Entitlements (Flags)

| Name | Type | Required | Secret | Public | Default | Description | Production requirement |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| `ENABLE_CHAT` | boolean | No | No | Yes | `false` | Controls visibility of chat interface module | `true` or `false` |
| `ENABLE_DOCUMENTS` | boolean | No | No | Yes | `false` | Controls visibility of document management UI | `true` or `false` |

---

### Private Infrastructure & Secrets (Server Only)

| Name | Type | Required | Secret | Public | Default | Description | Production requirement |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| `DATABASE_URL` | string | **Yes** | **Yes** | **No** | None | Async PostgreSQL connection string | **Must be PostgreSQL** (SQLite rejected) |
| `POSTGRES_USER` | string | No | No | No | `rag` | PostgreSQL database username | Strong custom database username |
| `POSTGRES_PASSWORD` | string | **Yes** | **Yes** | **No** | `rag` | PostgreSQL database user password | **Strong non-default password required** |
| `POSTGRES_DB` | string | No | No | No | `rag` | PostgreSQL database name | Custom production database name |
| `REDIS_URL` | string | **Yes** | **Yes** | **No** | `redis://localhost:6379/0` | Redis caching & async queue connection string | Active Redis instance with password auth |
| `JWT_SECRET` | string | **Yes** | **Yes** | **No** | `""` | Cryptographic key used to sign tokens | **Must be 32+ characters** (cannot be empty) |
| `OPENAI_API_KEY` | string | No | **Yes** | **No** | `""` | OpenAI platform API credential (reserved) | Masked in logs and settings representations |
| `GEMINI_API_KEY` | string | No | **Yes** | **No** | `""` | Google Gemini API credential (reserved) | Masked in logs and settings representations |

---

## 3. Security Boundary & Masking Rules

1. **Secret Masking via `SecretString`**: All sensitive values (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, API keys) inherit from `SecretString`. Output from `str()`, `repr()`, and Pydantic serialization is permanently replaced with `'**********'`, preventing accidental leakage in log aggregation tools.
2. **Strict Schema Mapping**: The `/api/v1/config` endpoint explicitly creates `PublicConfigResponse(...)`. It never calls `settings.model_dump()` and prunes keys, eliminating accidental disclosure of new private settings.
3. **Hex Color Validation**: Injected branding colors are strictly validated to prevent CSS injection vulnerabilities before reaching browser execution.
4. **Environment Isolation**: Production strictly enforces `DEBUG=false`, non-wildcard CORS, and real PostgreSQL connectivity.
