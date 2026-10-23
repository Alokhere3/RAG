# RAG Platform — Phase 0: Repository Intelligence & Foundation

**Status:** NOT STARTED  
**Phase:** 0  
**Objective:** Establish a clean, production-oriented repository foundation for a reusable, white-label, self-hosted RAG platform.

---

## 1. Phase Objective

This phase starts from an **empty directory**.

The objective is not to build RAG functionality yet.

The objective is to create a reliable project foundation on which all later phases can be implemented without repeatedly changing the architecture.

At the end of this phase, the repository must:

- Have a clear frontend/backend structure.
- Run locally.
- Start the backend successfully.
- Start the frontend successfully.
- Connect the backend to PostgreSQL.
- Have PostgreSQL configured with pgvector support.
- Have Redis available for future background jobs.
- Have Docker Compose capable of starting the infrastructure.
- Have environment-based configuration.
- Have basic health/readiness endpoints.
- Have backend and frontend test foundations.
- Have a clear README.
- Have no organization-specific hardcoded values.
- Have no production secrets committed to Git.
- Have basic logging and error-handling conventions.
- Have a foundation suitable for CI/CD later.

**Important:** Do not implement document ingestion, embeddings, retrieval, LLM calls, authentication, chat, or admin features in Phase 0.

---

# 2. Product Context

The final application will be a reusable RAG platform that can be deployed independently for different organizations.

Example:

```text
Client A
    |
    +-- Organization name
    +-- Bot name
    +-- Logo
    +-- Theme
    +-- LLM configuration
    +-- Embedding configuration
    +-- Storage configuration
    +-- Client documents
    |
    +-- Dedicated deployment

Client B
    |
    +-- Same application
    +-- Different configuration
    +-- Different documents
    |
    +-- Dedicated deployment
```

The application source code must remain generic.

Organization-specific values must come from configuration/environment variables.

Do not create logic such as:

```python
if organization == "ABC":
    ...
```

or:

```tsx
<h1>ABC Assistant</h1>
```

Instead, future phases will consume centralized configuration.

---

# 3. Architecture Direction

The initial architecture should be:

```text
                         Browser
                            |
                            v
                    +---------------+
                    |    Frontend   |
                    | React + TS    |
                    +-------+-------+
                            |
                         HTTP/API
                            |
                            v
                    +---------------+
                    |    FastAPI    |
                    |    Backend    |
                    +-------+-------+
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
        PostgreSQL        Redis       Future Services
        + pgvector
```

Docker Compose should orchestrate:

```text
frontend
backend
postgres
redis
```

A worker service may be added when Phase 5 introduces asynchronous document processing. Do not implement worker functionality in Phase 0 unless a minimal placeholder is required for Docker architecture.

---

# 4. Technology Decisions

## Backend

Use:

- Python
- FastAPI
- Pydantic
- Pydantic Settings
- SQLAlchemy
- Alembic
- PostgreSQL driver
- pytest
- pytest-asyncio where required

Do not introduce unnecessary frameworks.

---

## Frontend

Use:

- React
- TypeScript
- Vite
- ESLint
- A standard test framework appropriate for the project

Keep the frontend intentionally small in Phase 0.

The frontend only needs enough implementation to prove:

1. It starts.
2. It can load runtime/application configuration.
3. It can communicate with the backend health endpoint.

Do not build the chat UI yet.

---

## Database

Use:

- PostgreSQL
- pgvector extension

Do not create application tables yet unless a minimal migration infrastructure requires a database-level migration.

Database models will be introduced in Phase 2.

---

## Cache / Queue Infrastructure

Use:

- Redis

Phase 0 only proves that Redis is available and reachable.

Do not implement queues, workers, ingestion jobs, or rate limiting yet.

---

## Containerization

Use:

- Docker
- Docker Compose

Every service should have a clear responsibility.

---

# 5. Required Repository Structure

Create the following baseline structure:

```text
rag-platform/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── workers/
│   │   └── main.py
│   │
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   │
│   ├── alembic/
│   ├── alembic.ini
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── hooks/
│   │   ├── config/
│   │   ├── types/
│   │   └── App.tsx
│   │
│   ├── tests/
│   ├── public/
│   ├── package.json
│   └── Dockerfile
│
├── deployment/
│   ├── docker/
│   └── nginx/
│
├── docs/
│
├── .env.example
├── .gitignore
├── docker-compose.yml
├── README.md
└── LICENSE
```

The exact implementation may differ slightly if there is a strong technical reason, but responsibilities must remain separated.

---

# 6. Backend Requirements

## 6.1 FastAPI Application

Create the FastAPI application in:

```text
backend/app/main.py
```

The application must:

- Initialize FastAPI.
- Expose API versioning.
- Register routers.
- Configure application-level logging.
- Handle unexpected errors consistently.
- Expose health endpoints.

Expected API structure:

```text
/api/v1/...
```

---

# 7. Health Endpoints

Create:

```text
GET /health
GET /health/live
GET /health/ready
```

## `/health`

Purpose:

Basic application health.

Expected response:

```json
{
  "status": "ok"
}
```

---

## `/health/live`

Purpose:

Kubernetes/container/process liveness.

It should not depend on PostgreSQL or Redis.

Expected:

```json
{
  "status": "ok"
}
```

---

## `/health/ready`

Purpose:

Determine whether the application can serve requests.

It should check required dependencies:

- PostgreSQL
- Redis

Expected successful response:

```json
{
  "status": "ready",
  "dependencies": {
    "database": "ok",
    "redis": "ok"
  }
}
```

If a dependency is unavailable, the endpoint must clearly indicate failure.

Example:

```json
{
  "status": "not_ready",
  "dependencies": {
    "database": "ok",
    "redis": "unavailable"
  }
}
```

The exact HTTP status can be chosen according to standard readiness semantics.

---

# 8. Configuration System

Use Pydantic Settings.

Create a centralized settings object.

Example categories:

```text
Application
Database
Redis
Organization
LLM
Embeddings
Storage
Security
```

Do not spread direct `os.getenv()` calls throughout the codebase.

Bad:

```python
os.getenv("DATABASE_URL")
```

inside arbitrary services.

Preferred:

```python
settings.database_url
```

through a centralized configuration module.

---

# 9. `.env.example`

Create a complete example configuration.

It should contain placeholders such as:

```env
APP_ENV=development
APP_NAME=RAG Platform
APP_VERSION=0.1.0

ORGANIZATION_NAME=Demo Organization
BOT_NAME=AI Assistant
LOGO_URL=
PRIMARY_COLOR=

DATABASE_URL=postgresql://rag:rag@postgres:5432/rag
REDIS_URL=redis://redis:6379/0

LLM_PROVIDER=
LLM_MODEL=
OPENAI_API_KEY=
GEMINI_API_KEY=

EMBEDDING_PROVIDER=
EMBEDDING_MODEL=

STORAGE_PROVIDER=local
STORAGE_BUCKET=

JWT_SECRET=
```

Do not put real credentials in this file.

Use `.env` locally and ensure `.env` is ignored by Git.

---

# 10. Configuration Validation

Required configuration should fail fast.

For example:

- Invalid database URL.
- Invalid Redis URL.
- Missing required production secret.
- Invalid environment name.

Development may have relaxed requirements where appropriate.

Production must be stricter.

The error should clearly explain which configuration is invalid without exposing secret values.

---

# 11. PostgreSQL Setup

Docker Compose must start PostgreSQL.

Requirements:

- Persistent volume.
- Dedicated database.
- Dedicated user.
- Health check.
- pgvector extension available.

Verify:

```sql
SELECT extname FROM pg_extension;
```

The final environment should contain:

```text
vector
```

Do not build vector search yet.

---

# 12. Alembic Foundation

Initialize Alembic.

The project must support:

```bash
alembic upgrade head
```

and:

```bash
alembic downgrade -1
```

No business models are required yet.

The purpose of Phase 0 is to establish migration infrastructure.

---

# 13. Redis Setup

Docker Compose must start Redis.

Requirements:

- Persistent configuration where appropriate.
- Health check.
- Backend connectivity check.

Phase 0 only needs a simple connectivity test.

Do not add:

- Celery
- RQ
- custom queues
- rate limiter
- distributed locking

yet.

Those belong to later phases.

---

# 14. Docker Compose

Create:

```text
docker-compose.yml
```

Minimum services:

```text
frontend
backend
postgres
redis
```

Each service should:

- Have a clear container name or service name.
- Use environment configuration.
- Have health checks where appropriate.
- Use persistent storage for PostgreSQL.
- Have appropriate dependency ordering.

Avoid relying solely on:

```yaml
depends_on:
```

for application readiness.

The application itself must tolerate dependency startup ordering and expose accurate readiness.

---

# 15. Backend Dockerfile

The backend image must:

- Use a suitable Python base image.
- Install dependencies.
- Run the FastAPI application.
- Avoid running as root where practical.
- Avoid copying unnecessary files.
- Use a `.dockerignore`.

Do not put secrets into the image.

---

# 16. Frontend Dockerfile

The frontend image must:

- Install dependencies.
- Build the production application.
- Serve the production build.
- Use a suitable lightweight runtime.

Development tooling should not unnecessarily remain in the production runtime image.

---

# 17. Frontend Foundation

Create a minimal React application.

It should display:

```text
RAG Platform

Organization:
Demo Organization

Bot:
AI Assistant

Backend:
Connected
```

The purpose is to prove configuration and API connectivity.

Do not build:

- Chat
- Document management
- Login
- Dashboard
- RAG UI

yet.

---

# 18. Runtime Configuration

Avoid baking organization-specific configuration into the frontend build if the deployment model requires changing `.env` without rebuilding the frontend.

The architecture should leave room for runtime configuration such as:

```text
/config
```

or a generated runtime configuration file.

The final design should allow a client deployment to change:

```env
ORGANIZATION_NAME=Client Name
BOT_NAME=Client Assistant
LOGO_URL=...
```

without modifying source code.

The exact runtime-config mechanism can be finalized in Phase 1, but Phase 0 must not create an architecture that prevents it.

---

# 19. Logging

Establish structured, useful logging.

At minimum:

```text
timestamp
level
service
message
request_id
```

Example:

```text
2026-10-07T10:00:00Z INFO backend request completed request_id=abc123
```

Do not log:

- Passwords.
- API keys.
- JWTs.
- Authorization headers.
- Full document contents.
- Sensitive user data.

Create a consistent logging utility/configuration.

---

# 20. Error Handling

Create centralized API error handling.

Expected behavior:

```text
Validation error → structured 4xx
Authentication errors → later phase
Application error → structured 5xx
Unexpected error → generic public message + detailed internal log
```

Do not expose stack traces to API clients in production.

Example:

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "An unexpected error occurred.",
    "request_id": "abc123"
  }
}
```

The request ID allows developers to find the corresponding server-side log.

---

# 21. API Response Convention

Establish a consistent approach early.

Do not create arbitrary response structures for every endpoint.

Health endpoints may have their own simple structures.

For future business APIs, establish a predictable convention.

Example:

```json
{
  "data": {},
  "meta": {}
}
```

or another well-defined structure.

Document the decision.

Do not over-engineer a generic response wrapper if it provides no real value.

---

# 22. Testing Foundation

Backend testing must use pytest.

Create:

```text
backend/tests/
├── unit/
└── integration/
```

At minimum, implement tests for:

### Application startup

```text
test_application_starts
```

### Health

```text
test_health
test_liveness
test_readiness
```

### Configuration

```text
test_settings_load
test_invalid_configuration
```

### Database

```text
test_database_connection
```

### Redis

```text
test_redis_connection
```

---

# 23. Phase 0 Test Matrix

## Test 001 — Backend starts

**Action**

Start backend locally.

**Expected**

Application starts without exceptions.

**Status**

Must PASS.

---

## Test 002 — Health endpoint

```http
GET /health
```

Expected:

```http
200
```

and:

```json
{
  "status": "ok"
}
```

---

## Test 003 — Liveness

Stop PostgreSQL.

Call:

```http
GET /health/live
```

Expected:

Liveness still reports that the application process itself is alive.

---

## Test 004 — Readiness

Stop PostgreSQL.

Call:

```http
GET /health/ready
```

Expected:

Application reports database as unavailable.

---

## Test 005 — Redis readiness

Stop Redis.

Call:

```http
GET /health/ready
```

Expected:

Redis dependency reports unavailable.

---

## Test 006 — PostgreSQL

Connect to PostgreSQL.

Expected:

Successful connection.

---

## Test 007 — pgvector

Run:

```sql
SELECT extname FROM pg_extension;
```

Expected:

```text
vector
```

---

## Test 008 — Redis

Backend performs a Redis ping.

Expected:

```text
PONG
```

or equivalent successful connectivity.

---

## Test 009 — Missing environment variable

Remove a required environment variable.

Expected:

Application fails during configuration/startup with a clear error.

---

## Test 010 — Secrets are not committed

Search Git-tracked files for:

```text
OPENAI_API_KEY=
GEMINI_API_KEY=
JWT_SECRET=
AWS_SECRET_ACCESS_KEY=
```

Expected:

No real secrets.

---

## Test 011 — Frontend starts

Run frontend development server.

Expected:

Application loads successfully.

---

## Test 012 — Frontend → Backend

Frontend calls:

```http
GET /health
```

Expected:

Backend response is displayed.

---

## Test 013 — Docker Compose

Run:

```bash
docker compose up -d
```

Expected:

All required services start.

---

## Test 014 — Docker readiness

Verify:

```text
frontend
backend
postgres
redis
```

are running and healthy where health checks exist.

---

## Test 015 — Fresh startup

Remove containers and recreate them.

Expected:

Application can start from a clean environment.

---

## Test 016 — PostgreSQL persistence

Create a test database artifact.

Restart PostgreSQL.

Expected:

Persistent volume retains database state.

---

## Test 017 — Alembic

Run:

```bash
alembic upgrade head
```

Expected:

Migration succeeds.

Then:

```bash
alembic downgrade -1
```

Expected:

Migration rollback succeeds if there is a migration to roll back.

---

# 24. Code Quality Requirements

The implementation must follow:

- Separation of concerns.
- Dependency injection where useful.
- Small modules.
- Typed Python.
- TypeScript strict mode.
- No unnecessary global state.
- No duplicated configuration logic.
- No hardcoded client information.
- No dead code.
- No placeholder TODOs pretending to be implementations.
- No silently swallowed exceptions.

Avoid over-engineering.

The goal is a foundation, not an enterprise framework.

---

# 25. Security Requirements

Even in Phase 0:

- `.env` must be ignored.
- `.env.example` contains no secrets.
- Docker images must not contain secrets.
- Do not log secrets.
- Do not expose database ports unnecessarily in production configuration.
- Do not expose Redis publicly in production configuration.
- PostgreSQL should not be directly exposed to the public internet.
- Dependencies should be pinned or constrained appropriately.
- Use non-root containers where practical.

---

# 26. Documentation Requirements

Create/update:

```text
README.md
docs/architecture.md
docs/development.md
docs/environment.md
```

## README

Must explain:

- What the project is.
- Architecture overview.
- Local development.
- Docker startup.
- Environment configuration.
- Running tests.
- Current phase.
- What is not implemented yet.

---

## Architecture document

Explain:

```text
Frontend
   ↓
FastAPI
   ↓
PostgreSQL
Redis
```

and future planned components.

Clearly distinguish implemented components from planned components.

---

## Development document

Explain:

```bash
backend setup
frontend setup
docker setup
test commands
lint commands
migration commands
```

---

## Environment document

Document every environment variable:

| Variable | Required | Description |
|---|---|---|
| APP_ENV | Yes | Application environment |
| APP_NAME | Yes | Application name |
| ORGANIZATION_NAME | Yes | Client organization |
| BOT_NAME | Yes | AI assistant name |
| DATABASE_URL | Yes | PostgreSQL connection |
| REDIS_URL | Yes | Redis connection |
| LLM_PROVIDER | Later | LLM provider |
| LLM_MODEL | Later | LLM model |
| ... | ... | ... |

Clearly mark variables that belong to later phases.

---

# 27. Git Requirements

Initialize Git.

Create a meaningful initial commit after Phase 0 passes.

Suggested commit:

```text
chore: initialize rag platform foundation
```

`.gitignore` must include at least:

```text
.env
.env.*
!.env.example

__pycache__/
.pytest_cache/
.venv/

node_modules/
dist/
coverage/

*.log

.DS_Store
```

Do not blindly copy a generic `.gitignore`; verify it matches the actual project.

---

# 28. Definition of Done

Phase 0 is complete only when ALL of the following are true:

### Repository

- [ ] Repository initialized.
- [ ] Directory structure established.
- [ ] README created.
- [ ] Architecture documentation created.
- [ ] Development documentation created.
- [ ] Environment documentation created.

### Backend

- [ ] FastAPI starts.
- [ ] API versioning established.
- [ ] Configuration system implemented.
- [ ] Logging implemented.
- [ ] Error handling implemented.
- [ ] Health endpoint implemented.
- [ ] Liveness endpoint implemented.
- [ ] Readiness endpoint implemented.

### Frontend

- [ ] React + TypeScript application created.
- [ ] Frontend starts.
- [ ] Backend health connectivity demonstrated.
- [ ] No organization-specific hardcoded UI.

### Infrastructure

- [ ] PostgreSQL container works.
- [ ] pgvector works.
- [ ] Redis container works.
- [ ] Docker Compose works.
- [ ] Persistent PostgreSQL volume configured.
- [ ] Health checks configured.

### Database

- [ ] SQLAlchemy foundation exists.
- [ ] Alembic initialized.
- [ ] Migration command works.

### Testing

- [ ] pytest configured.
- [ ] Backend tests pass.
- [ ] Integration health tests pass.
- [ ] Configuration tests pass.
- [ ] Database connectivity test passes.
- [ ] Redis connectivity test passes.

### Security

- [ ] `.env` ignored.
- [ ] No secrets committed.
- [ ] No secrets logged.
- [ ] Containers don't require unnecessary root privileges.

---

# 29. Explicitly Out of Scope

Do NOT implement these in Phase 0:

```text
❌ User authentication
❌ JWT
❌ RBAC
❌ Document upload
❌ PDF parsing
❌ DOCX parsing
❌ OCR
❌ Chunking
❌ Embeddings
❌ Vector search
❌ Hybrid search
❌ Reranking
❌ LLM integration
❌ Chat
❌ Streaming
❌ Conversation history
❌ Admin dashboard
❌ Billing
❌ Multi-tenancy
❌ Kubernetes
❌ Cloud deployment
❌ Production monitoring
❌ Advanced RAG evaluation
```

These belong to later phases.

---

# 30. AI Agent Execution Instructions

If this phase is implemented using an AI coding agent, the agent must follow these rules:

### Rule 1 — Start from the actual repository

Inspect the current directory first.

Do not assume files exist.

---

### Rule 2 — Do not implement future phases

Only implement Phase 0 requirements.

If a future component is required structurally, create the minimum interface/folder needed without implementing future business functionality.

---

### Rule 3 — Verify instead of claiming

Do not say:

```text
"PostgreSQL is working."
```

unless it has actually been tested.

Instead report:

```text
PostgreSQL:
IMPLEMENTED
VERIFIED
```

---

### Rule 4 — Run tests

After implementation:

```bash
pytest
```

and relevant frontend checks must actually run.

---

### Rule 5 — Fix failures

If tests fail:

```text
identify root cause
→ fix
→ rerun
```

Do not mark the phase complete with known failures.

---

### Rule 6 — Review generated code

Check:

- Security.
- Configuration.
- Error handling.
- Dependency management.
- Docker configuration.
- Hardcoded values.
- Logging.
- Type safety.

---

### Rule 7 — Stop after Phase 0

Do not automatically proceed to Phase 1.

The phase must be reviewed and accepted before Phase 1 starts.

---

# 31. Final Phase 0 Report

At the end of implementation, produce a report using this format:

```text
PHASE 0 — COMPLETION REPORT

Status:
PASS / PARTIAL / FAILED

Repository:
PASS

Backend:
PASS

Frontend:
PASS

PostgreSQL:
PASS

pgvector:
PASS

Redis:
PASS

Docker:
PASS

Configuration:
PASS

Logging:
PASS

Error handling:
PASS

Tests:
X passed
Y failed

Security checks:
PASS

Known issues:
- ...

Deferred items:
- ...

Files created:
- ...

Files modified:
- ...

Next phase:
Phase 1 — Configuration & White-Label System
```

Do not mark Phase 0 as PASS if required acceptance criteria remain unverified.

---

# 32. Expected End State

When Phase 0 is finished, running:

```bash
docker compose up -d
```

should produce a system approximately like:

```text
┌────────────────────────────────────────────┐
│                RAG Platform                │
│                                            │
│  Frontend                                  │
│     │                                      │
│     ▼                                      │
│  FastAPI                                   │
│     │                                      │
│     ├───────────────┐                      │
│     ▼               ▼                      │
│ PostgreSQL        Redis                    │
│ + pgvector                                  │
│                                            │
└────────────────────────────────────────────┘
```

The application will **not yet answer questions**.

That is intentional.

Phase 0 proves that the foundation is sound.

The next phase will make the entire application dynamically configurable for any organization.
