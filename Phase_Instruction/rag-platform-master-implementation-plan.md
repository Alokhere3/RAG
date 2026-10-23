# Self-Hosted RAG Platform — Master Implementation Plan

**Target repository:** `F:\RAG`  
**Reported completed:** Phase 0 (foundation), Phase 1 (configuration/white-label)  
**Next phase:** Phase 2 (authentication and authorization)  
**Deployment model:** one dedicated deployment per client; not shared SaaS multi-tenancy.

This document is the master roadmap for the entire product: architecture, phase gates, implementation chunks, test cases, and final acceptance. Execute one chunk at a time. Do not ask Codex to implement every phase in one giant change.

## 1. Operating rules for Codex

For every chunk:

1. Inspect the repository, current branch, `git status`, existing tests, migrations, Docker state, and relevant documentation before editing.
2. Verify the predecessor phase is actually accepted. Historical reports are not proof that the current working tree still passes.
3. Search for existing implementation before creating a module, abstraction, dependency, or endpoint.
4. Before coding, report repository findings, scope, likely files, risks, and the acceptance/test checklist.
5. Implement only the named chunk. Do not begin the next chunk without explicit human acceptance.
6. Add tests for success, validation, failure, security, and regression behavior appropriate to the chunk.
7. Run focused tests first, then the relevant full regression suite, migrations, frontend build, and Docker checks where applicable.
8. Review the final diff for security, correctness, needless complexity, leaked secrets, unrelated edits, and scope drift.
9. Report exact commands, actual test counts, and outcomes. Never claim a check passed if it was not run.
10. If a check cannot run, mark it `BLOCKED/UNVERIFIED`, explain why, and give a reproducible command. Do not disguise it as PASS.
11. Stop and provide a chunk completion report. Wait for acceptance.
12. A final acceptance audit is read-only. Report defects; fix them in a separate implementation chunk.

### Mandatory chunk report

```text
PHASE X — CHUNK X.Y COMPLETION REPORT
Status: PASS / PARTIAL / FAILED / BLOCKED
Chunk and scope delivered:
Files created:
Files modified:
Migrations:
Tests added/updated:
Focused test results:
Backend regression:
Frontend tests/build:
Docker/integration verification:
Security review:
Acceptance criteria with evidence:
Warnings/technical debt:
Known issues:
Out-of-scope changes:
Recommendation: ACCEPT / REJECT / BLOCKED
Next chunk: only after explicit acceptance
```

## 2. Product and architecture decisions

### 2.1 Dedicated deployment per client

```text
Reusable source + same images
          |                       |
          v                       v
 Client A deployment        Client B deployment
 Dedicated DB/Redis         Dedicated DB/Redis
 Client A data/secrets      Client B data/secrets
```

This is **not** a shared SaaS multi-tenant system. Do not introduce `tenant_id`, cross-tenant filtering, tenant routing, or shared-customer data isolation unless the business model is explicitly changed. Within a client deployment, there can be multiple users with role-based access.

### 2.2 Existing stack to preserve

- FastAPI and Python backend
- Pydantic Settings configuration
- SQLAlchemy 2 async and Alembic
- PostgreSQL with pgvector
- Redis for rate limits and ephemeral coordination
- React + TypeScript + Vite frontend
- Docker Compose and Nginx reverse proxy
- Existing pytest and frontend test framework

Extend established patterns. Do not replace the stack merely for preference.

### 2.3 Architectural principles

- Client branding, assistant identity, model selection, API keys, and limits are configuration-driven, never hardcoded.
- Public configuration must never expose secrets, internal URLs, database credentials, Redis URLs, or provider keys.
- Every database schema change has an Alembic migration.
- All private APIs enforce authentication and server-side authorization.
- Uploads, parser work, network calls, retries, request sizes, and concurrency are bounded.
- Use structured logs and request IDs; never log passwords, tokens, cookies, API keys, raw document contents, or prompts by default.
- Store uploaded files on durable configured storage, not an ephemeral container layer.
- Treat uploaded and retrieved content as untrusted input.
- Use timeouts, bounded retries, clear failure states, idempotency where appropriate, and recovery procedures.
- Avoid premature enterprise features, speculative abstractions, and silent mock fallbacks in production.

### 2.4 High-level target architecture

```text
Browser / React SPA
       |
       v
Nginx reverse proxy
       |
       v
FastAPI API ------------------- Redis
       |                         |-- rate limiting
       |                         |-- ephemeral coordination
       v
PostgreSQL + pgvector
       |-- users and sessions
       |-- document metadata and ingestion jobs
       |-- chunks and embeddings
       |-- conversations and messages
       |
Durable file storage (configured volume/object storage)

Separate worker process for long-running ingestion/indexing tasks.
Configured embedding and LLM provider adapters for external/local inference.
```

A worker should be introduced when ingestion work is implemented, not as speculative infrastructure beforehand.

## 3. Phase roadmap

| Phase | Name | Main outcome | Dependency |
|---|---|---|---|
| 0 | Repository & Infrastructure Foundation | Reproducible, tested app/DB/Redis/Docker baseline | Starting point; previously reported complete |
| 1 | Configuration & White-Label Foundation | Runtime client branding and safe public config | Phase 0; previously reported complete |
| 2 | Authentication & Authorization | Users, secure sessions, roles, protected APIs | Phase 1 |
| 3 | Document Management | Secure upload/list/inspect/delete lifecycle | Phase 2 |
| 4 | Document Ingestion Pipeline | Safe extraction, job state, retries, worker recovery | Phase 3 |
| 5 | Embedding & Vector Indexing | Deterministic chunks and versioned pgvector embeddings | Phase 4 |
| 6 | Retrieval & RAG Core | Permission-aware retrieval, grounded generation, citations | Phase 5 |
| 7 | Chat & Conversation API | Persistent, access-controlled conversations and answers | Phase 6 |
| 8 | Administration & Operations | User/document/job administration and diagnostics | Phases 2–7 as relevant |
| 9 | Production Hardening & Client Deployment | Deployment, backup/restore, security, operability, release audit | All prior phases |

The roadmap can be changed only with a documented rationale after inspecting actual code. Keep the chunk gates even if the roadmap is adjusted.

---

# Phase 0 — Repository & Infrastructure Foundation

**Status:** previously reported complete; re-verify actual repository before further work.

## Objective and scope

Establish FastAPI, React/TypeScript/Vite, PostgreSQL/pgvector, Redis, SQLAlchemy async, Alembic, centralized configuration/errors/logging, health endpoints, Docker Compose, Nginx, and test infrastructure. Do not add product features during this phase.

Expected health endpoints:

```text
GET /health
GET /health/live
GET /health/ready
GET /api/v1/health
```

## Required test cases

- F0001: Backend application imports and starts.
- F0002: Liveness works independently of dependency health.
- F0003: Readiness fails when required PostgreSQL/Redis dependencies are unavailable.
- F0004: PostgreSQL connectivity and migrations work.
- F0005: pgvector extension is installed and usable.
- F0006: Redis connection and unavailable-Redis behavior are covered.
- F0007: Central error response has stable shape and request ID.
- F0008: Request ID propagates through logs/responses.
- F0009: Secret masking is tested.
- F0010: Docker health checks and service dependencies work.
- F0011: PostgreSQL data persists after container recreation.
- F0012: Backend runs non-root where configured.
- F0013: Frontend tests and production build pass.
- F0014: Production frontend image excludes unnecessary build tooling.
- F0015: No Phase 1+ product features were added.

## Acceptance gate

- [ ] Full backend tests pass.
- [ ] Full frontend tests/build pass.
- [ ] Migrations and pgvector are verified.
- [ ] Docker services are healthy.
- [ ] Persistence, non-root behavior, and secret masking are proven.
- [ ] Read-only Phase 0 audit records commands and actual counts.

Prior reports listed backend 29 tests and frontend 9 tests at Phase 0 completion. Treat these as historical numbers, not current acceptance evidence.

---

# Phase 1 — Configuration & White-Label Foundation

**Status:** previously reported accepted; preserve its contracts and regression coverage.

## Objective and scope

- Typed application settings and environment validation.
- Production config validation (debug, CORS, database, required secrets).
- Secret-aware settings representation.
- Public config schemas and `GET /api/v1/config`.
- Frontend runtime configuration, loading/error states, no build-time branding dependency.
- Runtime organization branding, assistant branding, theme, logo/favicon/title.
- Feature-flag foundation and deployment/white-label documentation.

Public configuration may include application, organization, assistant, branding, and feature fields only. Never expose DB credentials, Redis URLs, JWT secrets, LLM keys, internal hostnames, or internal ports.

## Required test cases

- W0001: Valid settings load.
- W0002: Invalid environment value is rejected; legacy alias normalization behaves as documented.
- W0003: Production rejects debug mode, wildcard CORS, unsafe DB configuration, and missing required secrets.
- W0004: Unsafe URL schemes are rejected.
- W0005: Secrets are masked in representations/logs.
- W0006: Public config schema excludes secrets and infrastructure details.
- W0007: `/api/v1/config` contract and camelCase aliases are correct.
- W0008: Frontend loads config at runtime.
- W0009: Loading and config-failure UI states work.
- W0010: Organization/assistant branding, logo, favicon, title, and theme update from config.
- W0011: One frontend image can be deployed with different runtime branding without rebuilding.
- W0012: Feature flags do not grant authorization.
- W0013: Nginx/reverse-proxy config endpoint works.
- W0014: No hardcoded client-specific names/branding in components.
- W0015: Full Phase 0 regression passes.

## Acceptance gate

- [ ] All public config fields are intentionally allowlisted.
- [ ] Runtime branding works without rebuilding the image.
- [ ] Production validation and secret isolation are tested.
- [ ] Documentation reflects dedicated deployments per client, not shared SaaS multi-tenancy.
- [ ] Read-only Phase 1 audit is accepted.

---

# Phase 2 — Authentication & Authorization Foundation

**Objective:** Establish the security boundary before private document APIs and retrieval exist.

## Scope

Users, email normalization/uniqueness, password hashing, login/logout, short-lived access JWTs, opaque refresh tokens, hashed refresh-session storage, rotation/revocation/reuse detection, `/me`, `ADMIN` and `USER` roles, protected API dependencies, frontend auth state, Redis login rate limiting, safe cookies, and security tests.

Defer OAuth, SSO/SAML, MFA, LDAP, social login, passwordless auth, generic fine-grained permission editors, and SaaS multi-tenancy.

## Data model

`users`: UUID, normalized unique email, password hash, display name, role, status (`active`, `inactive`, `suspended`), timestamps, last-login time.

`auth_sessions`: UUID, user FK, refresh token hash, expiry, created/revoked/last-used timestamps, optional user-agent/IP only if justified.

Use Argon2id where practical; a vetted fallback requires a documented reason. Never store plaintext passwords or raw refresh tokens server-side.

## Token and cookie rules

- Short-lived JWT access token; lifetime comes from config.
- Opaque cryptographically random refresh token; store only its hash.
- Refresh token only in HttpOnly cookie; access token in memory only.
- Never store access/refresh tokens in localStorage/sessionStorage.
- Validate signature, expiry, token type, subject, and user status.
- JWT algorithm must be allowlisted, never trusted from untrusted token input.
- Rotate refresh token on use; detect reuse of revoked tokens and revoke the defined session/family.
- Production cookie: HttpOnly, Secure, explicit SameSite and narrow path; no hardcoded domain.
- Document CSRF, CORS, and origin-validation model.
- Use the same public login error for unknown email and wrong password.

## API

```text
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

Use 401 for unauthenticated and 403 for authenticated-but-forbidden. `/me` never returns password hashes, raw refresh tokens, or session internals.

## Chunks

2.1 Architecture/security contract; 2.2 users/roles/migration; 2.3 password service; 2.4 access/refresh/session service; 2.5 auth API; 2.6 authorization dependencies; 2.7 frontend auth; 2.8 rate limiting/cookies/security logging; 2.9 end-to-end verification; 2.10 read-only audit.

## Required test cases

- A001: User creation and UUID generation.
- A002: Duplicate normalized email rejected by database constraint.
- A003: Password hash is non-plaintext and verification works.
- A004: Wrong password fails.
- A005: Unknown email and wrong password return equivalent generic errors.
- A006: Successful login returns safe user and access token.
- A007: Access JWT signature, expiry, type, and claims are validated.
- A008: Expired, malformed, wrong-type, and invalid-signature tokens return 401.
- A009: `/me` returns safe fields for authenticated user and 401 otherwise.
- A010: Refresh cookie has intended HttpOnly/Secure/SameSite/path attributes.
- A011: Refresh rotates token and invalidates the prior token.
- A012: Refresh-token reuse is detected and documented revocation policy applied.
- A013: Logout revokes session and clears cookie.
- A014: Revoked/expired refresh token is rejected.
- A015: Admin action allowed to ADMIN and denied with 403 to USER.
- A016: Inactive/suspended account is denied.
- A017: Redis login rate limiting works and fails safely.
- A018: Logs/responses contain no password, token, cookie, or secret.
- A019: Frontend session restoration, login failure, logout, and protected routes work.
- A020: 401 refresh retries original request at most once; no infinite loop.
- A021: Concurrent 401s share a single refresh operation.
- A022: Browser storage audit finds no tokens in localStorage/sessionStorage.
- A023: Alembic upgrade/downgrade/re-upgrade succeeds.
- A024: Phase 0/1 regression and Docker reverse-proxy auth flow pass.
- A025: No document, embedding, vector retrieval, LLM, RAG, or chat functionality added.

## Acceptance gate

- [ ] User/session migrations and all auth tests pass.
- [ ] Backend and frontend regression/build pass.
- [ ] Cookies/CORS verified through actual Nginx deployment.
- [ ] Security and scope audits pass.
- [ ] Read-only Phase 2 audit accepted.

---

# Phase 3 — Document Management

**Objective:** Securely manage source files and metadata without implementing full extraction, embeddings, or RAG.

## Data and API

Document metadata should include UUID, original display filename, generated storage key, detected content type, size, SHA-256 checksum, uploader ID, lifecycle status, timestamps, and safe metadata. Never expose absolute storage paths. Store bytes in durable configured storage (persistent local volume initially; optional object-storage adapter later), not an ephemeral container layer.

Proposed endpoints; align final naming with repository conventions:

```text
POST   /api/v1/documents
GET    /api/v1/documents
GET    /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}
```

List endpoints require pagination. Document access policy must be explicit: admin management and user ownership/visibility within the dedicated client deployment. Enforce authorization server-side.

## Safety requirements

- Configurable maximum upload size and request limits.
- Explicit supported formats, likely PDF, TXT, Markdown, and DOCX only if the parser stack is tested.
- Validate extension, declared MIME, and detectable file signature.
- Generate storage keys; never use user filename as a path.
- Prevent path traversal, overwrite, empty file, and malformed upload cases.
- Stream large uploads; avoid unbounded memory use.
- Clean up partial writes and handle DB/storage partial failure.
- Do not log document contents.
- Deletion must define behavior if metadata/file deletion partially fails.

## Required test cases

- D001: Valid supported file upload creates document metadata.
- D002: Unauthenticated upload returns 401.
- D003: Unauthorized role/owner operation returns 403 or documented anti-enumeration 404.
- D004: Empty file rejected.
- D005: Oversized file rejected with documented status.
- D006: Unsupported extension/type rejected.
- D007: MIME spoofing rejected where detectable.
- D008: Path traversal filename maps to safe generated key.
- D009: Duplicate upload behavior is deterministic and documented.
- D010: List endpoint pagination/order/limits work.
- D011: Get metadata returns safe fields only.
- D012: Unknown ID returns 404.
- D013: Delete handles file and metadata consistently.
- D014: Unauthorized deletion does not leak existence/private metadata.
- D015: Storage failure never reports success and cleans partial files.
- D016: Database failure after file write has cleanup/reconciliation behavior.
- D017: File survives container restart.
- D018: Concurrent uploads do not collide.
- D019: No absolute path, secret, or file content in response/logs.
- D020: Phase 0–2 regression passes.

## Acceptance gate

- [ ] Upload/list/get/delete and authorization work.
- [ ] Durable storage and upload bounds are tested.
- [ ] Migrations, partial failure, cleanup, and docs are complete.
- [ ] No parsing, embeddings, vector search, RAG, or LLM features yet.

---

# Phase 4 — Document Ingestion Pipeline

**Objective:** Safely extract normalized text and expose processing status. Do not create embeddings in this phase.

## Architecture and requirements

```text
Upload + durable file -> durable job record -> worker -> parser -> normalized text artifact/status
```

Use a worker process for long-running work. PostgreSQL remains the durable source of job state. If Redis is used for queue/coordination, define recovery for lost messages and crashed workers. Use a state machine such as `queued`, `processing`, `succeeded`, `failed`; add cancellation only if implemented end-to-end.

- Idempotent job handling and safe retries.
- Lease/timeout/recovery for crashed workers.
- Bounded retry count and backoff; do not retry permanent parser errors forever.
- Parser timeouts and resource limits.
- Maximum page/text size where appropriate.
- Detect image-only PDFs and report OCR requirement if OCR is deferred.
- Never execute uploaded content or shell commands.
- Treat extracted text as untrusted data.
- Store safe error code/message, parser version, and timestamps.
- Reprocessing must not create orphaned/duplicate artifacts.
- Authorized users can inspect job status.

## Required test cases

- I001: Valid text PDF extracts expected fixture text.
- I002: TXT/Markdown extraction and normalization are correct.
- I003: DOCX extraction works if DOCX is declared supported.
- I004: Corrupt/empty file ends in controlled failure.
- I005: Image-only PDF reports OCR-needed/unsupported, not false success.
- I006: Parser timeout is bounded and produces failure status.
- I007: Worker crash during processing is recoverable.
- I008: Transient error retries with bounded backoff.
- I009: Permanent parser error is not retried indefinitely.
- I010: Duplicate job delivery is idempotent.
- I011: Concurrent workers cannot corrupt final state.
- I012: Oversized extracted content is bounded.
- I013: Malicious filenames/content cannot execute commands or escape storage.
- I014: Status endpoint enforces authorization.
- I015: Deleting a document during/after ingestion has consistent behavior.
- I016: Parser/version metadata is persisted.
- I017: Logs contain no raw document text or secrets.
- I018: Phase 0–3 regression passes.

## Acceptance gate

- [ ] Job state machine, retries, recovery, and worker health are tested.
- [ ] Parser fixtures and failure cases pass.
- [ ] OCR limitations and supported formats are documented.
- [ ] No embeddings/vector/RAG/LLM work yet.

---

# Phase 5 — Embedding & Vector Indexing

**Objective:** Produce versioned chunks and embeddings and index them in PostgreSQL/pgvector.

## Requirements

- Small embedding-provider interface; start with one configured provider.
- Provider/model/API key configured per deployment, never public or hardcoded.
- Explicitly document whether text leaves client infrastructure for a remote provider.
- Deterministic configurable chunk size/overlap and chunking version.
- Preserve document ID, sequence, page/section metadata, and checksum.
- Reject empty/pathological chunks and enforce size limits.
- Record provider/model/version/dimensions with index metadata.
- Never mix incompatible embedding dimensions/models silently.
- Bounded batches, provider timeouts, rate limits, and retries.
- Re-indexing must have defined atomic switch/rollback behavior.
- Document deletion removes/tombstones chunks and vectors according to policy.
- Avoid logging document text or vectors.

## Required test cases

- E001: Chunking fixture is deterministic.
- E002: Overlap and chunk-size contract are correct.
- E003: Empty text yields no invalid vectors.
- E004: Long text is bounded into valid chunks.
- E005: Page/section/document metadata is preserved.
- E006: Embedding provider success returns expected vector shape.
- E007: Provider timeout/retry is bounded.
- E008: Provider rate limiting backs off safely.
- E009: Invalid vector dimensions are rejected.
- E010: Missing provider key gives clear safe error.
- E011: API keys do not leak in config/API/logs.
- E012: Duplicate ingestion does not duplicate index records.
- E013: Re-indexing preserves consistency on success and failure.
- E014: Partial batch failure is not marked complete incorrectly.
- E015: pgvector insert and similarity query work against PostgreSQL.
- E016: Model change cannot silently mix incompatible vectors.
- E017: Document deletion removes/tombstones associated chunks/vectors.
- E018: Phase 0–4 regression passes.

## Acceptance gate

- [ ] One configured provider works end-to-end.
- [ ] Chunking/index metadata is deterministic and versioned.
- [ ] pgvector dimensions/index and migrations are verified.
- [ ] Rate limits, retries, partial failures, re-indexing, and deletion are tested.
- [ ] Data-egress/cost configuration is documented.
- [ ] No user-facing RAG answers yet.

---

# Phase 6 — Retrieval & RAG Core

**Objective:** Implement permission-aware retrieval and grounded answer generation independent of chat UI.

## Pipeline

```text
Query -> validate identity/request -> embed query -> retrieve authorized chunks
      -> deduplicate/rank/context budget -> LLM provider -> answer + source citations
```

Start with vector retrieval and a testable interface. Add hybrid/lexical retrieval or reranking only if measurements justify it. Start with one configured LLM provider and a minimal adapter. Mock providers are for deterministic tests, never a silent production fallback that fabricates answers.

## Security and quality requirements

- Apply authorization/document filters before retrieved text enters model context.
- Never rely on frontend filtering.
- Treat retrieved text as untrusted and potentially prompt-injection-bearing.
- System instructions must distinguish retrieved data from trusted instructions.
- Never put secrets/private deployment config in prompts.
- Enforce context/token limits and provider timeouts.
- Validate provider output and return citations only for actually retrieved sources.
- When evidence is weak/absent, state that evidence is insufficient; do not fabricate facts/citations.
- Log safe IDs, latency, and usage metadata where available, not raw prompts/documents by default.
- Provider/model and data egress must be explicit deployment config.

## Required test cases

- R001: Relevant query retrieves relevant fixture chunks.
- R002: No-match query produces explicit insufficient-evidence behavior.
- R003: Query embedding failure is handled safely.
- R004: LLM timeout/rate limit has bounded failure/retry behavior.
- R005: Context budget is enforced deterministically.
- R006: Every citation maps to a retrieved document/chunk.
- R007: No citation is fabricated when no source was retrieved.
- R008: Prompt injection in a document is treated as untrusted data.
- R009: A document cannot prompt the model to disclose deployment secrets.
- R010: Unauthorized documents are excluded before LLM context construction.
- R011: Deleted/unindexed documents are not retrieved.
- R012: Duplicate chunks are deduplicated per policy.
- R013: Malformed provider output is validated/rejected.
- R014: Missing provider key/config fails clearly without leaking secrets.
- R015: Provider/model selection is configuration-driven.
- R016: Token/context limits and timeout behavior are tested.
- R017: Usage/latency metadata is safely recorded if supported.
- R018: Phase 0–5 regression passes.

## Acceptance gate

- [ ] Retrieval is testable without UI/HTTP.
- [ ] Permission filters are enforced before model context.
- [ ] Grounding/citations and insufficient-evidence behavior pass tests.
- [ ] Prompt-injection tests pass.
- [ ] Provider/data-egress settings are documented.
- [ ] No conversation UI/streaming yet.

---

# Phase 7 — Chat & Conversation API

**Objective:** Deliver persistent, authenticated conversations that use the tested RAG core.

## Proposed API

```text
POST   /api/v1/conversations
GET    /api/v1/conversations
GET    /api/v1/conversations/{id}
DELETE /api/v1/conversations/{id}
POST   /api/v1/conversations/{id}/messages
```

Use pagination and bounded page sizes. Enforce conversation ownership/admin policy. Persist only product-relevant messages, citation metadata, and safe usage metadata; do not persist hidden chain-of-thought. Define retention/deletion policy before storing sensitive chats. Implement non-streaming first; add streaming only after contract, cancellation, and cleanup behavior are tested.

## Required test cases

- C001: Create conversation.
- C002: List own conversations with stable pagination.
- C003: Get own conversation succeeds.
- C004: Access to another user's conversation is denied without leaking existence per policy.
- C005: Send message invokes RAG and persists answer.
- C006: Citations map to real sources.
- C007: Provider failure leaves consistent message/job state and safe error.
- C008: Retry behavior does not duplicate responses where idempotency is supported.
- C009: Delete follows documented retention policy.
- C010: Message pagination and ordering are stable.
- C011: Oversized prompts are rejected/bounded.
- C012: Concurrent messages have defined consistent behavior.
- C013: Unauthenticated requests return 401.
- C014: Ownership and role boundaries are enforced server-side.
- C015: If streaming is enabled, disconnect cancels/cleans work correctly.
- C016: Logs contain no secrets or raw private prompts by default.
- C017: Phase 0–6 regression passes.

## Acceptance gate

- [ ] Non-streaming chat works with RAG core.
- [ ] Ownership, pagination, persistence, citations, errors, and deletion are tested.
- [ ] Streaming is tested end-to-end or explicitly deferred.

---

# Phase 8 — Administration & Operations

**Objective:** Allow client admins to operate the deployment without direct database edits.

## Scope

Implement only useful admin workflows: user list/create/deactivate/reactivate and role changes; document and ingestion status; retry safe failed jobs; non-secret configuration diagnostics; health and basic operational metrics; clear UI loading/error/empty states. Avoid a generic admin platform or speculative permission editor.

Security: every admin route uses centralized authorization; protect against locking out the last administrator or document a recovery path; audit role/security-sensitive changes; diagnostics never show secrets; retry only safe/idempotent work; never return stack traces, raw prompts, document text, or environment variables.

## Required test cases

- O001: Admin can list/manage users within policy.
- O002: Normal user cannot manage users (403).
- O003: Role change is authorized and audited.
- O004: Normal user cannot change roles.
- O005: Last-admin deactivation follows a safe documented policy.
- O006: Admin can view safe document/job status.
- O007: Retry of failed job is safe/idempotent.
- O008: Retry of completed job has deterministic defined behavior.
- O009: Configuration diagnostics expose no secrets.
- O010: Dependency outage produces accurate health/degraded state.
- O011: UI loading/error/empty states work.
- O012: Admin action audit captures actor/action/time without sensitive payload.
- O013: Stack traces/internal errors are not exposed.
- O014: Phase 0–7 regression passes.

## Acceptance gate

- [ ] Routine admin workflows are usable and protected.
- [ ] Sensitive admin actions are auditable.
- [ ] Diagnostics are actionable but secret-safe.

---

# Phase 9 — Production Hardening & Client Deployment

**Objective:** Prove a client can install, configure, upgrade, back up, restore, and operate the product on dedicated infrastructure.

## Deployment requirements

- Documented clean installation path and supported versions.
- Production configuration validation before startup.
- Secrets injected through client-approved environment/secrets mechanism; never committed or baked into images.
- Persistent volumes for PostgreSQL and uploaded files.
- DB/Redis ports internal-only by default.
- TLS/reverse-proxy guidance, request-size/timeouts, resource limits, health/readiness, and worker counts documented.
- Migrations run as a controlled deployment step, not concurrently from every replica.
- Upgrade/rollback compatibility policy documented.
- Client-specific configuration template contains no real secrets.

## Backup and restore

Document and test PostgreSQL backup, uploaded-file backup, consistency between file storage and DB metadata, restore into a clean environment, verification, retention, encryption, access control, and recovery assumptions. A backup is not accepted until a restore has actually succeeded.

## Security and resilience

- Production fails closed on missing/unsafe settings.
- Explicit CORS allowlist, correct TLS/cookie settings, rate limits and request-size limits.
- Dependency/security scan and secret scan; triage critical/high findings.
- Safe log redaction and retention.
- Data retention/deletion and credential rotation guidance.
- Verify every private endpoint's authorization.
- Test Redis/provider outage, worker restart, allowed-size upload, concurrent requests, DB pool behavior, vector retrieval at representative scale, and graceful recovery.
- Document remote provider data egress and client responsibility.

## Required test cases

- P001: Clean production-style install succeeds from docs.
- P002: Missing production secret fails safely.
- P003: Wildcard CORS in production is rejected.
- P004: Database/Redis are not publicly exposed by default.
- P005: Data persists after restart.
- P006: PostgreSQL backup is created and verified.
- P007: Backup restores to clean environment and data is verified.
- P008: File backup/restore is consistent with metadata.
- P009: Migration upgrade works on supported existing data.
- P010: Upgrade failure/rollback procedure is documented and tested where feasible.
- P011: Secret scan finds no committed secrets.
- P012: Dependency findings are triaged and documented.
- P013: Redis outage has controlled degradation.
- P014: Provider timeout is bounded and does not hang worker/request indefinitely.
- P015: Worker restart recovers pending/leased jobs.
- P016: Maximum allowed upload uses bounded resources.
- P017: Unauthorized private API scan finds no exposure.
- P018: Logs contain no tokens, keys, passwords, or private content by default.
- P019: A clean operator can follow installation docs.
- P020: A clean operator can follow restore docs.
- P021: Branding/config changes without image rebuild.
- P022: Full backend tests pass.
- P023: Full frontend tests and production build pass.
- P024: Production Docker smoke tests pass.

## Acceptance gate

- [ ] Clean install is reproducible.
- [ ] Backup and restore are actually verified.
- [ ] Security/dependency findings are triaged.
- [ ] Resource and failure behavior are bounded.
- [ ] Documentation is sufficient for a client operator.
- [ ] No release blocker remains in the final read-only audit.

---

# Cross-phase testing strategy

Use several layers; a passing UI test alone is insufficient.

1. **Unit tests:** settings, password/token utilities, permission rules, upload validation, normalization/chunking, provider adapters with mocked transport, ranking/citation mapping, conversation state.
2. **Integration tests:** disposable PostgreSQL/pgvector and Redis for constraints, migrations, transactions, locks, token rotation, rate limiting, vector queries, file/metadata consistency, and job claiming/retries.
3. **API tests:** request/response contracts, status codes, error contract, authorization, pagination, limits, retries/idempotency, no internal/secret leakage.
4. **Frontend tests:** runtime config, loading/error/empty states, auth restoration, protected routes, upload/job states, conversation/citation rendering, and no browser token storage.
5. **End-to-end tests:** config loads; admin logs in; user uploads file; ingestion completes; embeddings index; question returns grounded citations; unauthorized access is denied; logout/refresh revocation works; restart preserves data; backup restores.
6. **Security tests:** malformed/expired credentials, privilege escalation, IDOR, path traversal, MIME spoofing, oversized requests, rate limits, secret/log leakage, prompt injection, unauthorized retrieval, CSRF/CORS/cookie behavior.

If remote embedding/LLM calls cost money or are nondeterministic, ordinary CI must use deterministic mocks. Keep a separate opt-in integration suite for real provider credentials; never claim a real-provider test passed if it was not run.

# Global acceptance matrix

| ID | Area | Evidence required |
|---|---|---|
| G001 | Deployment model | Dedicated deployment per client; no accidental SaaS tenancy |
| G002 | Runtime config | White-label settings work without rebuilding image |
| G003 | Secret safety | No secret leakage through API/logs/UI |
| G004 | Database | All schema changes have tested migrations |
| G005 | Authentication | Every private endpoint is protected |
| G006 | Authorization | Role/ownership enforced server-side |
| G007 | Upload safety | Size/type/path limits tested |
| G008 | Storage | Durable, backed up, and recoverable |
| G009 | Ingestion | Bounded processing, retries, and recovery |
| G010 | Embeddings | Provider/model/version/dimension validated |
| G011 | Retrieval | Permission filters before LLM context |
| G012 | Grounding | Citations map to actual retrieved sources |
| G013 | Prompt injection | Retrieved text treated as untrusted data |
| G014 | Chat | Ownership, pagination, persistence tested |
| G015 | Administration | Privileged actions authorized and audited |
| G016 | Operations | Health/failure states actionable |
| G017 | Deployment | Clean install verified |
| G018 | Backup | Restore succeeds and is verified |
| G019 | Regression | All previous phase tests pass |
| G020 | Scope boundary | No unapproved future-phase functionality |
| G021 | Documentation | Operator can deploy and troubleshoot |
| G022 | Build | Frontend/backend/container builds pass |
| G023 | Security audit | Findings triaged and blockers resolved |
| G024 | Completion report | Evidence-based PASS/PARTIAL/FAIL |

# Read-only final audit template (required at each phase end)

```text
PHASE X — ACCEPTANCE AUDIT
Audit mode: READ-ONLY
Overall status: PASS / PARTIAL / FAIL
1. Repository/Git inspection:
2. Scope review:
3. Database/migration review:
4. Backend tests (exact command/count):
5. Frontend tests (exact command/count):
6. Production build:
7. Docker build/health:
8. API contract checks:
9. Security checks:
10. Regression:
11. Documentation:
12. Acceptance matrix:
13. Known issues:
14. Deferred work:
15. Files created:
16. Files modified:
17. Commands/evidence:
18. Recommendation: ACCEPT / REJECT / BLOCKED
```

The auditor must not edit code, dependencies, tests, formatting, migrations, or configuration. If a failure is found, report and stop. Fix in a separate implementation chunk, then rerun the audit.

# Codex prompt to begin any chunk

Copy and fill in the phase/chunk ID each time:

```text
You are implementing one bounded chunk of the Self-Hosted RAG Platform in F:\RAG.
Read the master implementation plan and the current phase/chunk instructions first.

Before editing:
1. Inspect repository, branch, Git status, existing implementation, tests, migrations, and Docker state relevant to this chunk.
2. Confirm predecessor phases and report any baseline mismatch.
3. Search for existing code before adding abstractions.
4. State the chunk scope, proposed files, risks, and acceptance/test checklist.

Non-negotiable:
- Implement only the named chunk; do not begin the next chunk.
- This is a dedicated deployment per client, not shared SaaS multi-tenancy.
- Do not add tenant_id or cross-tenant routing/filters.
- Extend existing config, errors, logging, DB, API, and frontend patterns.
- Every database change requires an Alembic migration.
- Add automated success, failure, validation, security, and regression tests.
- Never log passwords, tokens, cookies, keys, or raw private document content.
- Never store plaintext passwords or raw refresh tokens server-side.
- Never put access/refresh tokens in localStorage/sessionStorage.
- Do not weaken security or delete tests to make tests pass.
- Do not implement later-phase features outside this chunk.
- Run focused tests, relevant regression suites, and applicable migrations/build/Docker checks.
- Review the final diff for security, unrelated changes, and scope drift.
- Report exact commands and results. Never invent test results.
- Mark unavailable verification BLOCKED/UNVERIFIED.
- Stop after this chunk and wait for explicit acceptance.

After implementation, provide the required chunk completion report.
```

For audit chunks, add: `AUDIT MODE IS READ-ONLY. Do not change files. Run checks, collect evidence, report failures, and stop.`

# Recommended execution sequence

```text
Re-verify Phase 0/1 baseline
 -> Phase 2 Authentication & Authorization
 -> Phase 3 Document Management
 -> Phase 4 Ingestion Pipeline
 -> Phase 5 Embedding & Vector Indexing
 -> Phase 6 Retrieval & RAG Core
 -> Phase 7 Chat & Conversation API
 -> Phase 8 Administration & Operations
 -> Phase 9 Production Hardening & Client Deployment
```

Every phase has chunk-level gates and a read-only final audit. A failed gate pauses work; it does not authorize skipping tests or moving forward.

# Final product acceptance definition

The first client release is acceptable only when a clean client environment can be installed from documentation; branding/config can change without rebuilding; admin and user access are secure; all private endpoints enforce authorization; supported documents can be uploaded within limits; ingestion is safe and observable; embeddings are indexed correctly; retrieval respects permissions; answers are grounded with valid citations and honest insufficient-evidence behavior; conversations persist with ownership checks; logs do not expose secrets/private content; data survives restart; backup/restore has been executed successfully; dependency/security findings are triaged; and full tests, builds, migrations, Docker checks, and critical end-to-end journeys pass.

**Guiding principle:** build the smallest complete and testable slice at a time, prove behavior before claiming completion, and do not sacrifice correctness, data isolation, or operational reliability for speed.
