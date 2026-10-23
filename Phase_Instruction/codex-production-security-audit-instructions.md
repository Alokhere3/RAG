# Codex Instructions — Production Security & Configuration Audit

**Repository:** `F:\RAG`  
**Audit mode:** READ-ONLY  
**Deployment model:** One dedicated deployment per client; no shared SaaS multi-tenancy.  
**Goal:** Independently verify security-sensitive parameters and production readiness from source to runtime, then produce an evidence-backed report and remediation plan. Do not modify anything.

## Mission

Audit every security-sensitive setting, environment variable, runtime parameter, deployment option, network boundary, and data-handling control. Trace each parameter from definition through validation to its actual consumer. Determine effective source/precedence, safe default, failure behavior, exposure risk, and test evidence. Do not assume the previous release report is correct without independently checking available evidence.

## Non-negotiable rules

1. Inspect repository path, branch, commit, Git status, and docs first.
2. Do not modify source, tests, dependencies, configs, secrets, database, containers, volumes, firewall, or services.
3. Never print or report raw secret values, tokens, database URLs, complete environment dumps, or provider keys.
4. Do not run destructive commands, migrations, restore operations, credential rotation, production load tests, or service restarts.
5. Do not call external providers using real credentials unless explicitly authorized and a safe read-only check is documented.
6. Do not assume a setting is enforced because it exists in `.env.example` or documentation; trace runtime usage.
7. Separate tests actually run from tests merely inspected and prior-reported results.
8. Mark unavailable evidence `UNVERIFIED`, not PASS.
9. Do not claim 100% verified if any applicable category was not inspected.
10. Keep the dedicated-per-client deployment model; do not introduce tenant IDs or shared-tenant assumptions.
11. Stop after the audit and remediation plan. Fix nothing.

## Procedure

### 1. Establish baseline
- Confirm repository, branch, commit, Git status and relevant uncommitted changes.
- Read the master implementation plan and deployment/security runbooks.
- Identify current environment without exposing secrets.
- List inspected files and inaccessible areas.

### 2. Build a complete configuration inventory
Search settings classes/validators, environment reads, `.env` templates, Pydantic Settings, Compose, Dockerfiles, Nginx, Alembic, startup/preflight scripts, CI workflows, frontend runtime config, `VITE_*`, and hardcoded fallbacks.

Inventory at least:

| Field | Required detail |
|---|---|
| Parameter | Exact setting name |
| Category | Auth, network, storage, LLM, etc. |
| Definition | File/class |
| Runtime consumer | File/function |
| Source/precedence | Environment, env file, default, Compose, code |
| Default | Safe description; never show secret defaults |
| Validation | Type, range, allowlist, production checks |
| Effective state | Present/missing/defaulted/invalid/unknown |
| Exposure | API, frontend, logs, container, none known |
| Failure behavior | Fail closed/fail open/fallback/crash/unknown |
| Evidence | File/line/test/command |
| Verdict | PASS/FINDING/UNVERIFIED/NOT APPLICABLE |

Never include actual secret values. Do not include guessable hashes/fingerprints of weak secrets.

### 3. Verify precedence and effective runtime behavior
Trace environment variables, `.env`/`env_file`, Pydantic defaults, Compose interpolation, container environment, runtime frontend configuration, build-time variables, and hardcoded fallbacks. Identify divergence across local, test, staging, and production configuration. Determine whether changing each high-risk parameter requires restart, rebuild, or migration.

### 4. Inspect unsafe configurations and failure paths
Check missing/empty/placeholder production secrets, weak JWT secrets, wildcard CORS, debug mode, SQLite in production, HTTP URLs where HTTPS is required, insecure cookies, unsupported JWT algorithms, invalid limits/timeouts/retries, invalid vector dimensions, missing provider keys, unsafe filesystem paths, public DB/Redis ports, verbose logs, missing volumes, and unsafe backup destinations. Find tests proving rejection; if none exist, record the gap without changing files.

### 5. Trace exposure paths
Inspect public config, health/readiness/version endpoints, admin diagnostics, exception handlers, request/response logs, auth errors, ingestion/provider errors, backup manifests/logs, frontend bundles/source maps, Docker image/build metadata, CI artifacts, and test fixtures. Look for credentials, tokens, cookies, private document text, prompts, filesystem paths, and stack traces.

### 6. Safely inspect runtime evidence
Use read-only checks only. If containers are running, inspect service name, image, health, published ports, mounts, user, and security options without printing environment values. Never restart services, change network rules, run migrations, alter volumes, or test restore on a live target. If runtime access is unavailable, mark it UNVERIFIED and provide a safe non-production verification command.

## Required audit categories

### A. Application configuration
Settings schema/validators; environment enum; production checks; defaults/fallbacks; unused/duplicate variables; secret masking; settings caching/reload; startup validation; docs-vs-code drift; public config allowlist; runtime branding.

### B. Secrets
JWT/database/Redis/LLM/embedding/encryption/backup/admin-bootstrap/CI credentials. Check source and Git history, frontend bundles, image layers, build args, logs, diagnostics, snapshots, fixtures, `.gitignore`, file permissions, placeholder rejection, rotation procedure, least privilege, and secret exposure through repr/serialization. Never quote a leaked value; recommend rotation if exposure is possible.

### C. Authentication, authorization and sessions
Password hashing and parameters; JWT algorithm/signature/claims/expiry/type; issuer/audience if used; access-token lifetime; refresh-token entropy/hash/rotation/reuse/revocation/expiry; concurrent refresh; logout; cookie HttpOnly/Secure/SameSite/Path/Domain; CORS/CSRF/origin; login rate limiting and account enumeration; inactive/suspended users; admin bootstrap/recovery/last-admin safeguards; ownership and IDOR checks; frontend token storage and refresh concurrency. Produce a route-by-route private API authorization matrix.

### D. Network, TLS, proxy and CORS
Nginx routes/upstreams; TLS termination and HTTPS behavior; HSTS guidance where applicable; CORS allowlist/credentials; trusted proxy headers/client IP; host header; request-size limits/timeouts; SSE/WebSocket proxy behavior; security headers/CSP; public DB/Redis/debug ports; Docker network reachability; SSRF if URL-fetch exists; provider egress. Clearly state whether TLS is terminated in Nginx, an external proxy, or elsewhere.

### E. Docker and host runtime
Non-root users; pinned images/dependencies; multi-stage builds; `.dockerignore`; no secrets in ARG/layers/labels; minimal runtime; permissions; capabilities/privileged mode; read-only filesystem/tmpfs/resource limits where appropriate; health checks; restart/graceful shutdown; volumes/networks/ports; CPU/memory/PID limits; vulnerability scanning; production image excludes development tooling.

### F. PostgreSQL, SQLAlchemy, Alembic and pgvector
Connection URL source/validation; TLS for remote DB; least-privilege DB role; pool sizing/timeouts; session lifecycle; raw SQL/parameterization; constraints/foreign keys; migration order/repeatability/deployment policy; pgvector extension/index strategy; backup consistency; data retention; no unnecessary public exposure. Do not execute migrations.

### G. Redis
Auth/ACL/TLS assumptions; network exposure; key namespaces/TTLs; atomic rate limits; outage behavior; queue durability; memory/eviction; retries/backoff; sensitive values in keys; persistence. Identify durable source of truth and intentional exceptions.

### H. Upload and storage
Request/file limits at proxy and app; extension allowlist; declared MIME vs magic bytes; parser allowlist; generated storage keys; path traversal/symlink; partial upload cleanup; atomic writes; persistent volume; permissions; malware scanning decision; archive bombs if supported; parser limits; download authorization/content disposition; deletion consistency/orphan cleanup; encryption/access control; sensitive logs.

### I. Ingestion workers
Job state transitions; atomic claims/leases; crash recovery; retryable vs permanent errors; max attempts/idempotency; concurrency/timeouts/resources; graceful shutdown; poison jobs; deletion during processing; safe errors; queue durability/lost-job recovery; re-index consistency; no execution of uploaded content.

### J. Embeddings and vector index
Provider/model/API key; client data egress; timeout/retry/backoff/rate limits/batch/cost; input token limits; dimensions/model compatibility; index versioning/re-indexing; partial failures; deletion/stale vectors; provider fallback; no silent production mock; no sensitive vector/text logs; performance assumptions.

### K. RAG and LLM
Prompt separation; retrieved text treated as untrusted; tool permissions enforced server-side; no secrets in prompts; authorization filters applied before LLM context; document readiness; context budget; prompt/response limits; timeouts/retries/rate/cost ceilings; sanitized errors; citations map to actual retrieved chunks; no fabricated citations; insufficient-evidence behavior; prompt injection/exfiltration tests; cross-user access; prompt/completion retention; streaming cancellation.

### L. Conversations and streaming
Ownership; pagination; message size/role validation; server-controlled roles; retry/idempotency; concurrent ordering; SSE auth/proxy timeout/disconnect; incomplete turn consistency; citation safety; deletion/retention; no hidden reasoning persisted; no private content in logs.

### M. Admin and diagnostics
Server-side role checks on all admin routes; user/role/status changes and audit trail; last-admin protection/recovery; safe idempotent job retries; no secret values in diagnostics; no environment dump endpoint; minimal health output; safe admin bootstrap/password recovery; no default production admin password.

### N. Logging, monitoring and privacy
Structured logs/request IDs; redact passwords/tokens/cookies/API keys; avoid prompts/document/message bodies by default; PII minimization; traceback exposure; log levels/debug; rotation/retention/access; disk exhaustion; health/readiness semantics; metrics without sensitive high-cardinality labels; alerts for auth failures, refresh reuse, worker/provider/backup failures and disk exhaustion; clock consistency; incident response.

### O. Backup and disaster recovery
DB/file consistency; manifest integrity/checksums; restore verification; encryption/access control; least-privilege credentials; retention/capacity; off-host protection; RPO/RTO; runbook; partial failure; no secret leakage in logs; ransomware/deletion protection; distinguish actual restore evidence from documentation claims. Do not execute backup/restore against production.

### P. Supply chain and CI/CD
Lockfiles/reproducibility; dependency and base-image vulnerabilities; integrity; static analysis/type checking/lint; secret scanning; SAST/container scanning; CI permissions/token scope; branch protections/approvals; build provenance; release gates; unreviewed deployment risk; dependency update policy/SLA. If scanning unavailable, mark unverified.

### Q. Frontend/browser
Runtime config vs build-time `VITE_*`; secrets/source maps in bundle; XSS/unsafe HTML/Markdown; `dangerouslySetInnerHTML`; external links; CSP; token memory/storage; CSRF/cookie behavior; API base URL validation; errors/telemetry; dependency audit; production source maps; private-response caching.

### R. Resource exhaustion
Verify actual enforcement for HTTP body, uploads/count, concurrent uploads, parser pages/text, worker concurrency, retries, DB pool, Redis memory, provider calls/cost, prompt/response length, pagination, SSE connections, timeouts, rate limits, disk/temp files. Identify which layer enforces each limit.

## Required deliverables

If report-file creation has not been explicitly authorized, return the report in the Codex response without changing files.

1. Executive decision: `PASS`, `PASS WITH CONDITIONS`, `FAIL`, or `UNVERIFIED`; release recommendation; date; repository/commit; scope and gaps.
2. Complete parameter inventory.
3. Findings with evidence and severity.
4. Route-by-route private API authorization matrix.
5. Exposure matrix for API, diagnostics, logs, frontend, images, backups, CI artifacts.
6. Exact commands/results and distinction between run, inspected-only, prior-reported, blocked.
7. Prioritized remediation plan.
8. Final go/no-go with explicit unverified items.

Finding template:

```text
ID:
Title:
Severity: CRITICAL / HIGH / MEDIUM / LOW / INFO
Category:
Affected files/lines:
Parameter(s):
Evidence:
Attack/failure scenario:
Impact:
Likelihood/context:
Exploit prerequisites:
Recommended remediation:
Required regression tests:
Release blocker: YES / NO
Confidence: HIGH / MEDIUM / LOW
```

Use evidence-based severity and avoid duplicate findings for one root cause.

## Production go/no-go criteria

An unconditional PASS requires evidence that all applicable items below hold:

- No known unresolved critical/high security finding.
- Production config fails closed on unsafe values.
- No secrets in source, frontend bundle, logs, APIs, diagnostics, image layers or CI output.
- Every private route enforces server-side auth and authorization.
- Refresh rotation/revocation/reuse behavior is verified.
- CORS, CSRF, cookies and TLS architecture are coherent.
- DB/Redis are not unnecessarily publicly exposed.
- Upload/parser limits are enforced.
- Ingestion is bounded and recoverable.
- Retrieval authorization occurs before LLM context construction.
- Prompt-injection, citations and insufficient-evidence behavior have tests.
- Provider timeout/rate/cost behavior is bounded.
- Persistence and backup/restore are proven.
- Dependency/image scans are performed or marked unverified.
- Clean install and runbooks are validated.
- Full regression/build checks pass.
- Warnings are triaged.
- Client responsibilities and data egress are documented.

If a critical category is unverified, do not claim 100% verification. Use `PASS WITH CONDITIONS` or `UNVERIFIED`.

## Safe command guidance

Start with:

```powershell
Set-Location F:\RAG
git status --short
git branch --show-current
git log -1 --oneline
```

Inspect test settings before running tests to ensure they cannot touch production databases, real providers, or production volumes. Do not run `Get-ChildItem Env:` or any command that dumps secrets. Filter Docker inspection output to safe metadata only. Run tests, builds, dependency scans, secret scans, and image scans only if available and safe; report exact tool versions and exit statuses. Do not assume tools exist.

## Final Codex response format

```text
PRODUCTION SECURITY & CONFIGURATION AUDIT

Status: PASS / PASS WITH CONDITIONS / FAIL / UNVERIFIED
Recommendation: RELEASE / CONDITIONAL RELEASE / BLOCK RELEASE
Repository:
Branch/commit:
Working tree:
Audit mode: READ-ONLY

Summary:
Parameters inventoried:
PASS:
Findings:
Critical:
High:
Medium:
Low:
Unverified categories:

Category results:
A. Configuration:
B. Secrets:
C. Authentication/authorization:
D. Network/TLS/CORS:
E. Docker/runtime:
F. PostgreSQL/Alembic/pgvector:
G. Redis:
H. Upload/storage:
I. Ingestion:
J. Embeddings:
K. RAG/LLM:
L. Conversations/streaming:
M. Admin/diagnostics:
N. Logging/monitoring/privacy:
O. Backup/restore:
P. Supply chain/CI:
Q. Frontend/browser:
R. Resource limits:

Configuration inventory:
Private API authorization matrix:
Exposure matrix:
Findings:
Commands executed:
Not verified:
Required remediation (P0/P1/P2/P3):
Final decision:
Audit integrity: No files or runtime state were modified.
```

**Start with repository inspection, complete every applicable category, produce the evidence-based report, and stop. Do not edit or fix anything during this run.**
