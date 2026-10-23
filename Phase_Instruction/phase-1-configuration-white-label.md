# Phase 1 — Configuration & White-Label System

**Project:** Reusable Self-Hosted RAG Platform  
**Phase:** 1  
**Status:** Planned  
**Predecessor:** Phase 0 — Repository Foundation & Infrastructure

## 1. Phase Objective

Establish the configuration-driven, white-label foundation for the RAG platform.

Target deployment model:

```text
Same application
      +
Same Docker images
      +
Client-specific configuration
      =
Independent client deployment
```

No client-specific source-code modification should be necessary.

---

## 2. Scope

### In Scope

- Central configuration contract
- Pydantic Settings hardening
- Environment validation
- Public/private configuration separation
- Runtime configuration API
- Configuration response schema
- Configuration tests
- Production safety validation
- Runtime frontend configuration
- Organization and assistant branding
- Runtime theme variables
- Logo and favicon configuration
- Page metadata
- Feature flags
- `.env.example`
- Deployment configuration documentation
- End-to-end white-label verification
- Security and regression audits

### Explicitly Out of Scope

```text
Authentication
JWT / refresh tokens
RBAC
Users
Organizations database model
Multi-tenancy
Document upload
PDF parsing
OCR
Chunking
Embeddings
Vector storage/search
Hybrid search
Reranking
LLM providers
Prompt management
RAG orchestration
Chat
Streaming
Conversation history
Admin dashboard
Billing
Usage tracking
Analytics
Kubernetes
Cloud-specific infrastructure
Object storage integration
```

---

## 3. Configuration Architecture

Phase 1 establishes three configuration layers.

### Layer A — Private Server Configuration

Backend-only values:

```text
DATABASE_URL
REDIS_URL
SECRET_KEY
OPENAI_API_KEY
GEMINI_API_KEY
```

These must never be returned to the browser.

### Layer B — Public Application Configuration

Safe for browser consumption:

```text
organization name
assistant name
logo URL
favicon URL
primary color
secondary color
enabled public features
application version
```

Exposed through:

```http
GET /api/v1/config
```

### Layer C — Frontend Runtime State

```text
GET /api/v1/config
        ↓
ConfigProvider
        ↓
useAppConfig()
        ↓
Components
        ↓
CSS variables
```

The frontend must not read server secrets or server `.env` files.

---

# 4. Chunk Structure

Phase 1 consists of nine implementation chunks:

```text
Phase 1
│
├── 1.1 Configuration Contract & Architecture
├── 1.2 Backend Configuration Hardening
├── 1.3 Public Configuration API
├── 1.4 Frontend Runtime Configuration
├── 1.5 White-Label Theme & Branding
├── 1.6 Feature Flag Foundation
├── 1.7 Deployment Configuration & Documentation
├── 1.8 End-to-End White-Label Verification
└── 1.9 Phase 1 Acceptance Audit
```

Each chunk is independently implemented, tested, reviewed, and accepted before proceeding.

---

# 5. Chunk 1.1 — Configuration Contract & Architecture

## Objective

Define exactly what configuration exists and where it may be consumed.

Inspect the Phase 0 configuration implementation before modifying it.

### Configuration Categories

#### Application

```text
APP_NAME
APP_VERSION
ENVIRONMENT
DEBUG
LOG_LEVEL
```

#### Organization

```text
ORGANIZATION_NAME
ORGANIZATION_LOGO_URL
ORGANIZATION_WEBSITE_URL
```

#### Assistant

```text
ASSISTANT_NAME
ASSISTANT_DESCRIPTION
ASSISTANT_AVATAR_URL
```

#### Branding

```text
PRIMARY_COLOR
SECONDARY_COLOR
ACCENT_COLOR
FAVICON_URL
```

#### API

```text
API_PREFIX
CORS_ORIGINS
```

#### Frontend Behavior

Only introduce useful, currently required flags, for example:

```text
ENABLE_CHAT
ENABLE_DOCUMENTS
```

Do not create speculative configuration for every future feature.

#### Infrastructure

Existing Phase 0 settings remain:

```text
DATABASE_URL
REDIS_URL
```

### Deliverables

Create/update as required:

```text
backend/app/core/config.py
backend/app/schemas/config.py
docs/configuration.md
docs/white-label.md
.env.example
```

### Acceptance Criteria

- [ ] Every configuration variable has a defined owner.
- [ ] Every setting is classified public or private.
- [ ] Secrets cannot accidentally enter public configuration.
- [ ] No client identity is hardcoded.
- [ ] Configuration naming is consistent.
- [ ] No speculative RAG configuration is introduced.

---

# 6. Chunk 1.2 — Backend Configuration Hardening

## Objective

Turn the Phase 0 settings foundation into a production-quality configuration system.

Use Pydantic Settings with:

- Type validation
- Defaults
- Required settings
- Environment validation
- URL validation
- Enum validation
- Color validation
- CORS validation
- Production safety validation

### Environment Types

Use an enum:

```text
development
testing
staging
production
```

### Production Safety

Examples:

```text
production + DEBUG=true
```

must be rejected or explicitly prevented.

Likewise:

```text
production + wildcard CORS
```

should be rejected unless deliberately supported.

### Secret Handling

Use appropriate secret types where practical:

```python
database_url: SecretStr
redis_url: SecretStr
```

Never log secret values.

### Configuration Access

Maintain a single configuration access pattern:

```python
settings = get_settings()
```

Avoid scattered:

```python
os.getenv(...)
```

throughout the codebase.

### Required Tests

- [ ] Valid development configuration
- [ ] Valid production configuration
- [ ] Missing required setting
- [ ] Invalid environment
- [ ] Invalid URL
- [ ] Invalid color
- [ ] Invalid CORS
- [ ] Production DEBUG rejection
- [ ] Secret masking
- [ ] Settings caching

### Acceptance

All backend tests pass with zero failures.

---

# 7. Chunk 1.3 — Public Configuration API

## Objective

Expose safe runtime configuration to the frontend.

Endpoint:

```http
GET /api/v1/config
```

Conceptual response:

```json
{
  "application": {
    "name": "Knowledge Assistant",
    "version": "1.0.0"
  },
  "organization": {
    "name": "Example Organization",
    "logoUrl": "/assets/logo.svg",
    "websiteUrl": "https://example.com"
  },
  "assistant": {
    "name": "Knowledge Assistant",
    "description": "Ask questions about your organization's knowledge.",
    "avatarUrl": "/assets/assistant.png"
  },
  "branding": {
    "primaryColor": "#B08D57",
    "secondaryColor": "#1A1A1A",
    "accentColor": "#D4AF37",
    "faviconUrl": "/assets/favicon.ico"
  },
  "features": {
    "chat": false,
    "documents": false
  }
}
```

Actual defaults should be deliberately selected during implementation.

### Security Boundary

Never expose:

```text
DATABASE_URL
REDIS_URL
SECRET_KEY
JWT_SECRET
OPENAI_API_KEY
GEMINI_API_KEY
AWS credentials
internal filesystem paths
private environment variables
```

Do not return arbitrary environment-variable dumps.

### Schema

Use an explicit Pydantic response schema.

Do not use:

```python
settings.model_dump()
```

and then remove secrets.

Instead explicitly construct:

```python
PublicConfigResponse(...)
```

### Tests

- [ ] `GET /api/v1/config` returns 200.
- [ ] Response matches the public schema.
- [ ] Fake secrets are absent from the response.
- [ ] Configuration changes propagate to API output.
- [ ] Endpoint follows the `/api/v1` convention.

---

# 8. Chunk 1.4 — Frontend Runtime Configuration

## Objective

Remove the current dependency on build-time branding configuration.

The existing conceptual approach:

```text
VITE_ORGANIZATION_NAME
VITE_BOT_NAME
```

must no longer be the primary white-label mechanism.

Target:

```text
Browser
  ↓
React application
  ↓
GET /api/v1/config
  ↓
Runtime configuration
```

### Suggested Architecture

```text
frontend/src/config/
├── types.ts
├── api.ts
├── ConfigProvider.tsx
└── useAppConfig.ts
```

Potential usage:

```tsx
<ConfigProvider>
    <App />
</ConfigProvider>
```

Consumers use:

```tsx
const config = useAppConfig();
```

### Loading State

```text
Application boot
      ↓
Loading configuration
      ↓
Configuration loaded
      ↓
Render application
```

Do not render a partially branded application.

### Error State

Show a safe user-facing message such as:

```text
Unable to load application configuration.
Please contact the administrator.
```

Do not expose stack traces, internal URLs, or infrastructure details.

### API Abstraction

Continue using:

```text
frontend/src/services/api.ts
```

No component should directly call `fetch()` for configuration.

### Tests

- [ ] Config loading
- [ ] Successful response
- [ ] Loading state
- [ ] API failure
- [ ] Malformed response
- [ ] Missing optional fields
- [ ] Consumer component rendering

---

# 9. Chunk 1.5 — White-Label Theme & Branding

## Objective

Make the application genuinely white-label.

Runtime configurable properties:

### Organization

```text
organization name
logo
website
```

### Assistant

```text
assistant name
description
avatar
```

### Browser

```text
document.title
favicon
```

### Theme

```text
primary color
secondary color
accent color
```

### CSS Architecture

Introduce design tokens:

```css
:root {
    --color-primary: ...;
    --color-secondary: ...;
    --color-accent: ...;
}
```

Runtime configuration should populate the CSS variables.

```text
Config
 ↓
ThemeProvider
 ↓
CSS custom properties
 ↓
UI
```

### Color Validation

Never blindly inject arbitrary configuration values into CSS.

Validate the values before browser consumption. Prefer a constrained format such as valid hexadecimal colors unless a broader color grammar is deliberately required.

### Tests

- [ ] Organization name changes
- [ ] Assistant name changes
- [ ] Logo changes
- [ ] Primary color changes
- [ ] Secondary color changes
- [ ] Favicon changes
- [ ] Page title changes

All must work without source modification.

---

# 10. Chunk 1.6 — Feature Flag Foundation

## Objective

Create a controlled mechanism for enabling/disabling future capabilities.

Example:

```json
{
  "features": {
    "chat": false,
    "documents": false
  }
}
```

Initially, flags may control UI visibility.

### Security Rule

Feature flags are **not security controls**.

For example:

```text
ENABLE_ADMIN=true
```

must never replace authorization.

Authentication and RBAC will be implemented independently later.

### Architecture

```text
PublicConfig
      ↓
FeatureFlags
      ↓
React components
```

### Tests

- [ ] Feature enabled → visible
- [ ] Feature disabled → hidden
- [ ] Unknown feature → safely ignored

Do not implement features that do not exist yet.

---

# 11. Chunk 1.7 — Deployment Configuration & Documentation

## Objective

Make configuration usable by an actual client deployment team.

Update:

```text
.env.example
README.md
docs/configuration.md
docs/white-label.md
docs/deployment/
```

### Configuration Reference

Every variable should document:

| Property | Example |
|---|---|
| Name | `ORGANIZATION_NAME` |
| Type | string |
| Required | yes/no |
| Secret | yes/no |
| Public | yes/no |
| Default | value |
| Description | purpose |
| Production requirement | requirement |

### Deployment Model

Document:

```text
Client A
├── same Docker images
├── client .env
└── client branding

Client B
├── same Docker images
├── client .env
└── different branding
```

No code fork.

### Deployment Validation

Document:

```bash
docker compose up -d
docker compose ps
```

and:

```http
GET /api/v1/config
GET /health
GET /health/ready
```

---

# 12. Chunk 1.8 — End-to-End White-Label Verification

This is the most important functional verification.

## Configuration A

```text
Organization:
Acme Corporation

Assistant:
Acme Knowledge Assistant

Primary:
#123456
```

Verify the application.

## Configuration B

Change only configuration:

```text
Organization:
Example University

Assistant:
University Knowledge Assistant

Primary:
#654321
```

Verify:

```text
No source-code changes
No Docker image modification
No client-specific code fork
No frontend rebuild when runtime configuration is designed correctly
```

The UI must change accordingly.

### Verification Matrix

| Test | Expected |
|---|---|
| Change organization name | UI changes |
| Change assistant name | UI changes |
| Change logo | UI changes |
| Change favicon | Browser changes |
| Change primary color | UI theme changes |
| Change assistant description | UI changes |
| Disable feature | Feature disappears |
| Enable feature | Feature appears |
| Change DB URL | Public config unchanged |
| Change Redis URL | Public config unchanged |
| Add API key | API key never exposed |
| Restart containers | Configuration persists |
| Rebuild unnecessary | Runtime branding still works |

---

# 13. Chunk 1.9 — Phase 1 Acceptance Audit

This chunk is **audit only**. Do not add features during the audit.

The audit must:

1. Read the complete Phase 1 specification.
2. Inspect the entire repository.
3. Map requirements to implementation.
4. Run backend tests.
5. Run frontend tests.
6. Run frontend production build.
7. Run Docker Compose.
8. Verify runtime configuration.
9. Verify white-label switching.
10. Perform security audit.
11. Search for hardcoded branding.
12. Search for leaked secrets.
13. Search for scattered environment access.
14. Verify Phase 2+ functionality has not leaked into Phase 1.
15. Inspect Git diff/status.
16. Report findings without modifying code merely to make the audit pass.

---

# 14. Phase 1 Security Model

## Never Expose

```text
DATABASE_URL
REDIS_URL
SECRET_KEY
JWT_SECRET
OPENAI_API_KEY
GEMINI_API_KEY
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

Even if some do not exist yet.

## Public Configuration Must Be Allowlisted

Correct model:

```text
Private Settings
       │
       ▼
Public Config Mapper
       │
       ├── application
       ├── organization
       ├── assistant
       ├── branding
       └── features
              │
              ▼
           Browser
```

Never:

```text
Environment
    ↓
model_dump()
    ↓
Browser
```

---

# 15. Phase 1 Testing Strategy

## Backend

Test:

```text
Configuration unit tests
Validation tests
Public config API tests
Security tests
Existing Phase 0 tests
```

Do not target an arbitrary test count. Behavioral coverage matters more than test count.

## Frontend

Test:

```text
ConfigProvider
useAppConfig
loading state
error state
configuration rendering
theme application
feature flags
branding
```

## Integration

Verify:

```text
Docker
 ↓
Nginx
 ↓
Frontend
 ↓
/api/v1/config
 ↓
FastAPI
 ↓
Settings
```

---

# 16. Phase 1 Acceptance Matrix

| ID | Requirement | Result |
|---|---|---|
| C001 | Configuration contract | |
| C002 | Environment validation | |
| C003 | Production validation | |
| C004 | Secret classification | |
| C005 | Public config schema | |
| C006 | `/api/v1/config` | |
| C007 | No secret leakage | |
| C008 | Runtime frontend config | |
| C009 | Config loading state | |
| C010 | Config failure state | |
| C011 | Organization branding | |
| C012 | Assistant branding | |
| C013 | Runtime logo | |
| C014 | Runtime favicon | |
| C015 | Runtime page title | |
| C016 | Runtime theme | |
| C017 | Feature flags | |
| C018 | Configuration switching | |
| C019 | Docker integration | |
| C020 | Documentation | |
| C021 | Backend regression | |
| C022 | Frontend regression | |
| C023 | Security audit | |
| C024 | Phase boundary | |

---

# 17. Definition of Done

## Architecture

- [ ] Single configuration source of truth
- [ ] Public/private configuration boundary
- [ ] Runtime frontend configuration
- [ ] No client-specific source code

## Backend

- [ ] Configuration fully validated
- [ ] `/api/v1/config`
- [ ] Explicit public schema
- [ ] No secret leakage
- [ ] Production safety validation

## Frontend

- [ ] Runtime config provider
- [ ] No hardcoded organization branding
- [ ] No hardcoded assistant branding
- [ ] Runtime theme
- [ ] Runtime logo
- [ ] Runtime favicon
- [ ] Runtime title
- [ ] Feature flag foundation

## Deployment

- [ ] `.env.example`
- [ ] Configuration documentation
- [ ] Docker-compatible configuration
- [ ] Client deployment instructions

## Testing

- [ ] Backend tests pass
- [ ] Frontend tests pass
- [ ] Production build passes
- [ ] Docker stack passes
- [ ] White-label switching passes
- [ ] Security audit passes
- [ ] Phase 0 regression passes

---

# 18. Phase 1 Final Report

At the end, produce:

```text
PHASE 1 — CONFIGURATION & WHITE-LABEL COMPLETION REPORT

Status: PASS / PARTIAL / FAILED

Configuration: PASS
Backend: PASS
Public Config API: PASS
Frontend Runtime Config: PASS
White-Label Branding: PASS
Theme System: PASS
Feature Flags: PASS
Docker: PASS
Documentation: PASS
Security: PASS

Backend Tests: X passed / Y failed
Frontend Tests: X passed / Y failed

White-Label Verification: PASS / FAIL
Security Checks: PASS / FAIL
Regression: PASS / FAIL

Known Issues:
...

Deferred Items:
...

Files Created:
...

Files Modified:
...

Next Phase:
Phase 2 — ...
```

---

# 19. Recommended Execution Rules

Maintain the same phase-gated discipline used in Phase 0:

```text
Phase 1
   │
   ├── Chunk 1.1
   │     ↓
   │   Implement
   │     ↓
   │   Test
   │     ↓
   │   Review
   │
   ├── Chunk 1.2
   │     ↓
   │   Implement
   │     ↓
   │   Test
   │     ↓
   │   Review
   │
   ├── ...
   │
   └── Chunk 1.9
         ↓
       Audit
         ↓
     PASS / FAIL
         ↓
       Phase 2
```

## Phase 1 Agent Rules

1. Inspect the actual repository before modifying anything.
2. Implement only the current chunk.
3. Do not implement future RAG functionality.
4. Reuse existing Phase 0 infrastructure.
5. Do not duplicate configuration mechanisms.
6. Keep secrets strictly server-side.
7. Prefer explicit schemas over dynamic environment dumps.
8. Add tests with each implementation chunk.
9. Run regression tests after changes.
10. Review generated code for unnecessary complexity.
11. Do not claim functionality without verification.
12. Do not modify unrelated files.
13. Stop after the current chunk is complete.
14. Record blockers and non-blocking technical debt explicitly.

---

# 20. Phase 1 Success Definition

The phase is successful when a new client can be deployed conceptually like this:

```text
                    SAME CODEBASE
                         │
               ┌─────────┴─────────┐
               │                   │
               ▼                   ▼
          Client A              Client B
               │                   │
        Client config        Client config
               │                   │
               ▼                   ▼
        ┌────────────┐      ┌────────────┐
        │  Branding  │      │  Branding  │
        │  Config    │      │  Config    │
        └────────────┘      └────────────┘
               │                   │
               ▼                   ▼
        Independent          Independent
        deployment           deployment
```

The strongest acceptance criterion is:

> **A client-specific deployment can change its organization identity, assistant identity, branding, theme, and enabled features through configuration without modifying application source code or creating a client-specific code fork.**

Phase 1 should leave the project ready to begin the next core platform capability without introducing authentication, document processing, vector search, LLM, or RAG logic prematurely.
