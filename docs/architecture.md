# Architecture Overview

## 1. System Design

The RAG platform is designed as a modular, decoupled architecture enabling white-label distribution across single-tenant and multi-tenant deployments.

```text
                             Browser (Client)
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │       Frontend Runtime        │
                    │   React 19 + TypeScript + Vite│
                    └───────────────┬───────────────┘
                                    │ HTTP / REST
                                    ▼
                    ┌───────────────────────────────┐
                    │        FastAPI Backend        │
                    │   Python 3.13 + Pydantic v2   │
                    └───────┬───────────────┬───────┘
                            │               │
                            ▼               ▼
                    ┌───────────────┐ ┌───────────┐
                    │  PostgreSQL   │ │   Redis   │
                    │  + pgvector   │ │  Broker   │
                    └───────────────┘ └───────────┘
                            │
               (Future Ingestion & Inference)
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
         LLM Provider             Vector Embeddings
      (OpenAI / Gemini / Local) (Text Embeddings Engine)
```

---

## 2. Component Status

| Component | Technology | Phase 0 Scope | Future Phase Scope |
| :--- | :--- | :--- | :--- |
| **Frontend** | React, TypeScript, Vite | Baseline startup, status check, white-label shell | Interactive Chat UI, Document Management, Admin |
| **Backend** | FastAPI, Pydantic, SQLAlchemy | `/health`, `/health/live`, `/health/ready`, logging, error format | Document ingestion, Retrieval pipelines, RAG agent |
| **Relational DB** | PostgreSQL 16+ | Connection validation, Alembic baseline | Tenant data, document metadata, audit logs |
| **Vector DB** | pgvector extension | Extension validation (`SELECT extname FROM pg_extension;`) | Embeddings storage, HNSW/IVFFlat indexing |
| **Cache & Queue**| Redis 7+ | Connection & PING healthcheck | Async ingestion worker queue, rate limiting, caching |
| **Orchestration**| Docker Compose | Multi-container local execution | Production Kubernetes / Helm manifests |

---

## 3. White-Label Isolation

The source code contains zero client-specific branching:
- All client identifiers (`ORGANIZATION_NAME`, `BOT_NAME`, `LOGO_URL`, `PRIMARY_COLOR`) are delivered via environment variables or runtime configuration endpoints.
- Database access is managed through standardized data access layers without hardcoded organizational logic.
- Storage and LLM engines are abstracted behind interchangeable provider interfaces.

---

## 4. Architecture Specifications Index

- [Authentication & Authorization Architecture (Phase 2)](authentication.md)
- [Configuration System Reference (Phase 1)](configuration.md)
- [White-Label Branding System Guide (Phase 1)](white-label.md)
- [Client Deployment Runbook](deployment/README.md)
