# Client Deployment & White-Label Runbook

This guide instructs operations, DevOps, and deployment teams on provisioning and managing tenant-specific instances of the RAG Platform.

---

## 1. Multi-Client Deployment Model

The platform uses a **single immutable Docker image architecture**. A single set of pre-built Docker images (`rag-frontend` and `rag-backend`) serves all client deployments without recompilation, code modification, or client-specific forks.

```text
               Container Registry (Pre-built Artifacts)
               ├── rag-backend:latest
               └── rag-frontend:latest
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
   Deployment: Client A              Deployment: Client B
   ├── same Docker images            ├── same Docker images
   ├── client-a.env                  ├── client-b.env
   │   ORGANIZATION_NAME=Acme        │   ORGANIZATION_NAME=Example Uni
   │   PRIMARY_COLOR=#10B981         │   PRIMARY_COLOR=#7C3AED
   └── client branding assets        └── client branding assets
        ▼                                 ▼
   Acme AI Workspace                 Uni Knowledge Portal
   (Emerald Theme, Acme Logo)        (Purple Theme, Uni Logo)
```

### Key Guarantees
1. **No Code Forks**: All client-specific identity resides exclusively in environment variables and runtime endpoints.
2. **No Frontend Rebuild**: The frontend React application fetches runtime branding from `GET /api/v1/config` at browser boot time, eliminating client-specific `npm run build` steps.
3. **Zero Secret Leakage**: Private infrastructure parameters (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`) are strictly isolated from client-facing configuration payloads.

---

## 2. Directory Structure for Client Deployments

```text
/opt/deployments/
├── client-a/
│   ├── docker-compose.yml
│   └── .env
└── client-b/
    ├── docker-compose.yml
    └── .env
```

Each client deployment directory contains:
- `docker-compose.yml`: Pulls the unified images from the registry.
- `.env`: Contains client-specific branding, feature flags, and infrastructure connection strings.

---

## 3. Production Deployment Checklist

Before starting any production container, ensure the following constraints are met:

| Check | Requirement | Reason |
| :--- | :--- | :--- |
| **Environment** | `APP_ENV=production` | Enforces production security validations |
| **Debug Mode** | `DEBUG=false` | Prevents exposure of debug tracebacks and profiling endpoints |
| **CORS Origins** | Specific domains (e.g. `https://rag.client.com`) | Rejects wildcard `*` origins in production |
| **JWT Secret** | 32+ character high-entropy secret | Secures authentication tokens (production rejects default or empty secret) |
| **Secure Cookies** | `AUTH_COOKIE_SECURE=true` (auto-defaulted in production) | Ensures refresh tokens are only sent over HTTPS (F-05) |
| **Database** | PostgreSQL + pgvector | SQLite is rejected in production mode |
| **DB Credentials** | Non-default `POSTGRES_PASSWORD` | Default `rag:rag` credentials rejected in production (F-07) |
| **DB Roles** | `DATABASE_URL` → `rag_app`, `MIGRATION_DATABASE_URL` → `rag_migrator` | Least-privilege role separation (F-12B) |
| **Redis** | Authenticated `REDIS_URL` with `REDIS_PASSWORD` set | Unauthenticated default Redis rejected in production (F-07) |
| **Migrations** | `RUN_MIGRATIONS_ON_STARTUP=false` (default) | Decouple DDL from web server boot; run via CI/CD (F-12B) |
| **Colors** | Valid Hex `#RRGGBB` or `#RGB` | Guards against style injection |
| **Ports** | Dedicated host ports (e.g., 3001/8001 or standard 80/443 behind reverse proxy) | Avoids host port collisions with other services |

---

## 4. Deployment Procedure

### Step 1: Prepare Environment File
Copy `.env.example` into your client deployment directory:
```bash
cp .env.example .env
```

### Step 2: Configure Client Identity & Branding
Configure the white-label parameters in `.env`:
```bash
# Organization Branding
ORGANIZATION_NAME="Acme Corporation"
ORGANIZATION_LOGO_URL="https://assets.acme.com/logo.svg"
ORGANIZATION_WEBSITE_URL="https://acme.com"

# Assistant Persona
ASSISTANT_NAME="Acme Copilot"
ASSISTANT_DESCRIPTION="Ask questions about Acme policies, documents, and technical manuals."
ASSISTANT_AVATAR_URL="https://assets.acme.com/copilot-avatar.png"

# Theme Design Tokens
PRIMARY_COLOR="#0F766E"
SECONDARY_COLOR="#0F172A"
ACCENT_COLOR="#14B8A6"
FAVICON_URL="https://assets.acme.com/favicon.ico"

# Feature Entitlements
ENABLE_CHAT=false
ENABLE_DOCUMENTS=false
```

### Step 3: Launch Containers
Start the platform stack in detached mode:
```bash
docker compose up -d
```

---

## 5. Deployment Validation

After launching the platform, run the following verification steps:

### 1. Verify Container Health
Check that all services are running and reporting healthy:
```bash
docker compose ps
```
Expected output:
```text
NAME           IMAGE                 COMMAND                  SERVICE    STATUS
rag-backend    rag-backend:latest    "/app/deployment/doc…"   backend    Up (healthy)
rag-frontend   rag-frontend:latest   "/docker-entrypoint.…"   frontend   Up (healthy)
rag-postgres   pgvector/pgvector     "docker-entrypoint.s…"   postgres   Up (healthy)
rag-redis      redis:7-alpine        "docker-entrypoint.s…"   redis      Up (healthy)
```

### 2. Verify Liveness Probe
```bash
curl -i http://localhost:8001/health
```
Expected: `HTTP/1.1 200 OK`
```json
{
  "status": "ok",
  "app": "RAG Platform",
  "version": "0.1.0",
  "environment": "production"
}
```

### 3. Verify Readiness Probe
```bash
curl -i http://localhost:8001/health/ready
```
Expected: `HTTP/1.1 200 OK`
```json
{
  "status": "ready",
  "dependencies": {
    "database": "ok",
    "redis": "ok"
  }
}
```

### 4. Verify Public Configuration Endpoint
```bash
curl -i http://localhost:8001/api/v1/config
```
Expected: `HTTP/1.1 200 OK` containing client branding:
```json
{
  "application": {
    "name": "RAG Platform",
    "version": "0.1.0",
    "environment": "production"
  },
  "organization": {
    "name": "Acme Corporation",
    "logoUrl": "https://assets.acme.com/logo.svg",
    "websiteUrl": "https://acme.com"
  },
  "assistant": {
    "name": "Acme Copilot",
    "description": "Ask questions about Acme policies, documents, and technical manuals.",
    "avatarUrl": "https://assets.acme.com/copilot-avatar.png"
  },
  "branding": {
    "primaryColor": "#0F766E",
    "secondaryColor": "#0F172A",
    "accentColor": "#14B8A6",
    "faviconUrl": "https://assets.acme.com/favicon.ico"
  },
  "features": {
    "chat": false,
    "documents": false
  }
}
```

### 5. Verify Frontend Proxy Delivery
Ensure frontend reverse proxy routes configuration cleanly:
```bash
curl -i http://localhost:3001/api/v1/config
```
Expected: Same `HTTP/1.1 200 OK` JSON response forwarded from backend.

### 6. Verify Secret Isolation
Confirm that infrastructure secrets (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, API keys) are **completely absent** from the `/api/v1/config` payload.

---

## 6. Zero-Downtime Rebranding / Config Updates

To update branding, assistant persona, or feature flags:
1. Update the `.env` file with new values.
2. Restart the backend container:
   ```bash
   docker compose up -d backend
   ```
3. Refresh the browser. The frontend immediately reflects the updated identity and theme without building or re-tagging any Docker image.
