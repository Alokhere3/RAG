# RAG Platform

Production-ready, white-label, self-hosted Retrieval-Augmented Generation (RAG) platform.

---

## 📌 Project Overview

This repository provides an enterprise-grade, generic RAG platform architecture designed for independent, organization-specific deployments. All branding, virtual assistant persona, LLM connections, storage, and models are dynamically configurable without hardcoded client logic or client-specific code forks.

### Status: Phase 1 — Configuration & White-Label System

The platform features an immutable Docker container architecture where a single image pair (`rag-frontend` and `rag-backend`) is deployed across multiple clients purely via configuration.

### Implemented Capabilities

#### Phase 0: Foundation
- Asynchronous FastAPI backend with SQLAlchemy 2.0 and asyncpg
- PostgreSQL with pgvector extension enabled
- Redis cache and async coordinator
- React 19 + TypeScript + Vite frontend with Nginx reverse proxy
- Docker Compose multi-container orchestration with healthchecks
- Standardized health probes (`/health`, `/health/ready`)

#### Phase 1: White-Label & Configuration
- **Strongly-Typed Configuration Contract**: Explicit Pydantic schemas (`PublicConfigResponse`) and TypeScript interfaces.
- **Backend Configuration Hardening**: Production validation rules (`DEBUG=false`, non-wildcard CORS, PostgreSQL enforcement), URL validation, and hexadecimal color pattern enforcement.
- **Secret Masking**: Sensitive credentials (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, API keys) inherit from `SecretString` and are strictly masked (`**********`) in memory, logs, and serializers.
- **Public Configuration API**: Endpoint `GET /api/v1/config` exposing sanitized branding without secret leakage.
- **Frontend Runtime Configuration**: React `ConfigProvider` and `useAppConfig` loading dynamic branding at browser boot time with zero client rebuilds.
- **Dynamic CSS Design Tokens**: Custom properties (`--color-primary`, `--color-secondary`, `--color-accent`) injected at runtime into `:root` alongside document metadata (`document.title`, `favicon`).
- **Feature Flag Foundation**: Declarative `<FeatureGate>` and `useFeatureFlag()` gating UI visibility based on server entitlements.
- **Multi-Tenant Deployment Guide**: Runbook for single-image multi-tenant operations.

### Explicitly Out of Scope in Phase 1 (Reserved for Future Phases)
- User authentication & JWT login flows (Phase 2)
- Role-based access control (RBAC) (Phase 2)
- Document upload, OCR, parsing, and chunking (Phase 3/4)
- Embeddings and vector similarity search (Phase 4/5)
- LLM inference and chat engine (Phase 6+)

---

## 🏛 Architecture Overview

```text
                         Browser
                            │
                            ▼
                    ┌───────────────┐
                    │    Frontend   │  (Port 3001)
                    │  React + Vite │  Proxies /api & /health to backend
                    └───────┬───────┘
                            │
                         HTTP/API
                            │
                            ▼
                    ┌───────────────┐
                    │    FastAPI    │  (Port 8001)
                    │    Backend    │  GET /api/v1/config
                    └───────┬───────┘
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
        PostgreSQL                       Redis
        + pgvector                    (Port 6379)
        (Port 5432)
```

For comprehensive architectural design, see [docs/architecture.md](docs/architecture.md).

---

## 🚀 Getting Started

### Prerequisites
- Python 3.13+
- Node.js 24+
- Docker Engine 28+ & Docker Compose v2+

### 1. Environment Configuration
Copy `.env.example` into `.env`:
```bash
cp .env.example .env
```
Configure your organization name, assistant persona, and brand colors in `.env`. See [docs/configuration.md](docs/configuration.md) for the complete reference.

### 2. Launch with Docker Compose
Start all containers in detached mode:
```bash
docker compose up -d
```

### 3. Verify Deployment
Check container health and endpoints:
```bash
docker compose ps
curl -i http://localhost:8001/health
curl -i http://localhost:8001/health/ready
curl -i http://localhost:3001/api/v1/config
```

Access the frontend application at: **`http://localhost:3001`**

---

## 🧪 Running Tests

### Backend Test Suite (Pytest)
```bash
cd backend
.\.venv\Scripts\python.exe -m pytest tests/
```

### Frontend Test Suite (Vitest)
```bash
cd frontend
npm test
```

### Frontend Production Build
```bash
cd frontend
npm run build
```

---

## 📄 Documentation Index

- [Client Deployment & White-Label Runbook](docs/deployment/README.md)
- [Configuration System Reference](docs/configuration.md)
- [White-Label Branding System Guide](docs/white-label.md)
- [Architecture Specifications](docs/architecture.md)
- [Local Development Guide](docs/development.md)
