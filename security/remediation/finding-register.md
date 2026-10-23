# Canonical Security Finding Register

**Repository:** `F:\RAG`  
**Deployment Model:** Dedicated Self-Hosted Instance Per Client (Single-Tenant)  
**Baseline Date:** 2026-10-23  
**Status Decision:** **READY FOR INDEPENDENT VERIFICATION (All Chunks Remediated & Automated Test Gates Passed)**  

---

## 1. Executive Summary & Audit Reconciliation

This finding register establishes the canonical, reconciled truth for all security findings reported in the independent audit of 2026-10-23. The original audit report contained duplicated sections and ambiguous labeling around **F-12** (which referenced resource limits, upload limits, migration permissions, and missing supply-chain CI controls).

This register assigns stable identifiers (`F-01` through `F-11`, plus `F-12A`, `F-12B`, and `F-12C`), documents source-level and host-level evidence with verified paths and line numbers, and defines explicit acceptance criteria for each finding.

---

## 2. Tooling and Runtime Inventory (Chunk 0 Baseline)

| Tool / Runtime | Location / Source | Version | Operational Status |
| :--- | :--- | :--- | :--- |
| **Python** | Host / VirtualEnv | `3.13.9` | **AVAILABLE** |
| **Virtualenv Python** | `F:\RAG\backend\.venv\Scripts\python.exe` | `3.13.9` | **AVAILABLE** |
| **Backend Test Tooling** | `F:\RAG\backend\.venv\Scripts\pytest.exe` | `8.4.2` | **AVAILABLE** (101/103 unit pass, 106/106 integration pass from backend cwd) |
| **Node.js** | `C:\nvm4w\nodejs\node.exe` | `24.1.0` | **AVAILABLE** |
| **npm** | `C:\nvm4w\nodejs\npm.ps1` | `11.4.1` | **AVAILABLE** |
| **Frontend Test Tooling** | `frontend/node_modules/vitest` | `3.2.7` | **AVAILABLE** (45/45 vitest tests pass) |
| **Git** | `C:\Program Files\Git\cmd\git.exe` | `2.45.1.windows.1` | **AVAILABLE** (`master` branch, unborn initial commit) |
| **Docker** | `C:\Program Files\Docker\Docker\resources\bin\docker.exe` | `28.5.2` | **AVAILABLE** |
| **Docker Compose** | Docker Desktop plugin | `v2.40.3-desktop.1` | **AVAILABLE** |
| **Static Linter (Ruff)** | `C:\Users\AS\Anaconda3\Scripts\ruff.exe` | Installed | **AVAILABLE** |
| **Type Checker (Mypy)** | `C:\Users\AS\Anaconda3\Scripts\mypy.exe` | Installed | **AVAILABLE** |
| **pip-audit** | N/A | None | **NOT AVAILABLE** |
| **safety** | N/A | None | **NOT AVAILABLE** |
| **bandit** | N/A | None | **NOT AVAILABLE** |
| **semgrep** | N/A | None | **NOT AVAILABLE** |
| **trivy** | N/A | None | **NOT AVAILABLE** |
| **gitleaks** | N/A | None | **NOT AVAILABLE** |

---

## 3. Canonical Finding Register

### F-01 — Insecure `.env` NTFS Permissions and Secret Exposure
- **Audit Alias:** `F-01`
- **Reported Severity:** HIGH
- **Status:** `CONFIRMED`
- **Evidence:**
  - NTFS ACL check on `F:\RAG\.env`:
    `IdentityReference: Everyone`, `FileSystemRights: -1` (`FullControl`), `AccessControlType: Allow`.
  - NTFS ACL check on parent directory `F:\RAG`:
    `IdentityReference: Everyone`, `FileSystemRights: -1` (`FullControl`), `AccessControlType: Allow`.
  - `.env` contains 29 keys with live connection strings, secrets, and provider keys.
- **Affected File/Lines:** `F:\RAG\.env`, `F:\RAG`
- **Intended Fix:**
  - Remove `Everyone` grant from `F:\RAG\.env` and its containing folder; restrict ACL to authorized operator/service identities.
  - Provide a safe PowerShell ACL verification script that checks permissions without printing secrets.
  - Document a credential-by-credential rotation checklist for credentials residing in the exposed `.env`.
- **Acceptance Criteria:**
  - `git ls-files` does not list `.env`.
  - ACL on `.env` only grants access to authorized identities.
  - Credential rotation status is documented.

---

### F-02 — Docker Build-Context and Image Data Isolation
- **Audit Alias:** `F-02`
- **Reported Severity:** HIGH
- **Status:** `CONFIRMED`
- **Evidence:**
  - `backend/.dockerignore` lines 1–14 omits `dev.db` (180 KB SQLite database) and `data/` (`backend/data/storage`).
  - `backend/Dockerfile` line 31: `COPY --chown=appuser:appuser . /app` copies entire context into image.
  - Local SQLite database and storage directory are situated inside `backend/` and would be baked into image layers if built.
- **Affected File/Lines:** `backend/.dockerignore:1-14`, `backend/Dockerfile:31`, `backend/dev.db`, `backend/data/`
- **Intended Fix:**
  - Explicitly add `dev.db`, `*.db`, `data/`, `storage/`, uploads, backups, caches, and test artifacts to `backend/.dockerignore`.
  - Create a deterministic verification test using synthetic canary files proving unneeded files do not enter image/context.
- **Acceptance Criteria:**
  - Synthetic canaries absent from image context.
  - Docker build succeeds without including local database or storage artifacts.

---

### F-03 — Backup Fallback Writes Insecure Secrets to Dump
- **Audit Alias:** `F-03`
- **Reported Severity:** HIGH
- **Status:** `CONFIRMED`
- **Evidence:**
  - `deployment/scripts/backup.py` lines 73–77:
    ```python
    except FileNotFoundError:
        # Fallback if pg_dump is not in PATH during local offline testing
        print("[-] Warning: pg_dump not installed on host. Writing metadata marker.")
        with open(db_backup_file, "w") as f:
            f.write(f"POSTGRESQL_BACKUP_DUMP_URL={db_url}\n")
    ```
    Serializes raw `DATABASE_URL` (including plaintext password and host) into `database.dump` inside the archive.
- **Affected File/Lines:** `deployment/scripts/backup.py:73-77`
- **Intended Fix:**
  - Remove secret-writing fallback.
  - Fail closed with a nonzero exit code and explicit non-secret error if native backup tool is missing or fails.
  - Ensure partial temporary files are cleaned safely without deleting prior valid backups.
- **Acceptance Criteria:**
  - Missing `pg_dump` exits nonzero with error message; no connection URL or secret appears in generated archive.

---

### F-04 — Insecure Restore Archive Extraction and Unchecked Manifest Paths
- **Audit Alias:** `F-04`
- **Reported Severity:** HIGH
- **Status:** `CONFIRMED`
- **Evidence:**
  - `deployment/scripts/restore.py` lines 49–50:
    ```python
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=staging_extract_dir)
    ```
    Extracts archive without path validation, filter, or member traversal check.
  - `deployment/scripts/restore.py` lines 96–100:
    ```python
    for rel_path in files_manifest.keys():
        src = extracted_storage / rel_path
        dst = target_storage_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    ```
    Trusts manifest `rel_path` keys without path containment validation, allowing directory traversal / file overwrite.
- **Affected File/Lines:** `deployment/scripts/restore.py:49-50, 96-100`
- **Intended Fix:**
  - Validate every archive member before extraction (reject absolute paths, drive-qualified paths, UNC paths, `..` traversal, symlinks/hardlinks).
  - Validate manifest `rel_path` keys to guarantee they remain strictly within target directories.
  - Use safe extraction filter API and isolate staging directory.
- **Acceptance Criteria:**
  - Adversarial archives with traversal or symlinks are rejected before writing.
  - Valid archives restore correctly.

---

### F-05 — Authentication Cookie Security and CSRF/Origin Protection
- **Audit Alias:** `F-05`
- **Reported Severity:** HIGH
- **Status:** `CONFIRMED`
- **Evidence:**
  - `backend/app/core/config.py` lines 311–314:
    ```python
    auth_cookie_secure: bool = Field(default=False)
    ```
  - `backend/app/core/config.py` lines 446–473 (`validate_production_safety`): Does not require `auth_cookie_secure is True` in production.
  - `docker-compose.yml` lines 45–67: Does not pass `AUTH_COOKIE_SECURE` to backend container, defaulting to insecure HTTP cookies.
  - No CSRF token or origin validation for cookie-authenticated state-changing endpoints (`/refresh`, `/logout`).
- **Affected File/Lines:** `backend/app/core/config.py:311-314, 446-473`, `docker-compose.yml:45-67`, `backend/app/api/v1/endpoints/auth.py`
- **Intended Fix:**
  - Enforce `auth_cookie_secure=True` in production environment mode.
  - Inject `AUTH_COOKIE_SECURE` in Compose.
  - Add Origin / Referer validation and CSRF defenses for cookie-authenticated endpoints.
- **Acceptance Criteria:**
  - Production mode fails closed if cookies are not secure.
  - State-changing cookie requests require valid origin.

---

### F-06 — Plaintext HTTP Port Exposure and TLS Termination Topology
- **Audit Alias:** `F-06`
- **Reported Severity:** HIGH
- **Status:** `CONFIRMED` (Source/Compose level) / `NEEDS RUNTIME EVIDENCE` (Deployed Edge)
- **Evidence:**
  - `docker-compose.yml` lines 114–115:
    ```yaml
    ports:
      - "${FRONTEND_PORT:-3001}:80"
    ```
    Frontend publishes port 80 to all host interfaces by default.
  - Repository contains no reverse proxy TLS configuration or certificate configuration.
- **Affected File/Lines:** `docker-compose.yml:114-115`, `frontend/nginx.conf`, `deployment/nginx/nginx.conf`
- **Intended Fix:**
  - Document dedicated-per-client deployment topology (public TLS terminator / reverse proxy).
  - Configure Compose port bindings to bind to loopback (`127.0.0.1:${FRONTEND_PORT:-3001}:80`) or document strict network edge boundaries.
  - Provide preflight checklist to verify HTTPS redirection and HSTS.
- **Acceptance Criteria:**
  - Plaintext service ports not accessible from public interfaces.
  - Documented edge proxy configuration mandates TLS 1.3 / 1.2 with HSTS.

---

### F-07 — Fail-Closed Production Configuration & Default Credential Rejection
- **Audit Alias:** `F-07`
- **Reported Severity:** HIGH
- **Status:** `CONFIRMED`
- **Evidence:**
  - `backend/app/core/config.py` lines 224–250: Defaults to weak credentials (`rag:rag` and `redis://localhost:6379/0`).
  - `validate_production_safety` (lines 446–473) accepts default `rag:rag` credentials in production.
  - `docker-compose.yml` line 46: `APP_ENV: ${APP_ENV:-development}`.
  - Startup script runs `alembic upgrade head && uvicorn` without preflight validation.
- **Affected File/Lines:** `backend/app/core/config.py:224-250, 446-473`, `docker-compose.yml:46`, `backend/Dockerfile:40`
- **Intended Fix:**
  - Add fail-closed validation rejecting weak/default credentials (`rag`, `postgres`, `password`) in production.
  - Enforce explicit `APP_ENV=production` for production deployments.
  - Wire preflight configuration validation into startup/CI.
- **Acceptance Criteria:**
  - Application startup fails closed on default/weak credentials or missing configuration.
  - Local development remains functional when explicitly configured.

---

### F-08 — Redis Login Rate Limiter Fail-Open Outage Policy
- **Audit Alias:** `F-08`
- **Reported Severity:** MEDIUM
- **Status:** `CONFIRMED`
- **Evidence:**
  - `backend/app/services/auth/rate_limit.py` lines 25–27:
    ```python
    except Exception:
        logger.exception("LOGIN_RATE_LIMIT_UNAVAILABLE")
        return
    ```
    Fails open on any Redis connection or execution error, completely disabling brute-force protections.
  - `backend/tests/unit/test_rate_limit.py` lines 18–24:
    Directly tests and asserts that rate limiting fails open when Redis is unavailable.
- **Affected File/Lines:** `backend/app/services/auth/rate_limit.py:25-27`, `backend/tests/unit/test_rate_limit.py:18-24`
- **Intended Fix:**
  - Implement a bounded local in-memory fallback rate limiter with strict capacity and TTL limits, or fail closed with 503 Service Unavailable for authentication endpoints.
  - Eliminate unredacted stack trace logging on limiter errors.
- **Acceptance Criteria:**
  - Redis outage does not permit unlimited authentication attempts.
  - Memory usage remains bounded during extended outages.

---

### F-09 — Non-Atomic Refresh-Token Rotation Race Condition
- **Audit Alias:** `F-09`
- **Reported Severity:** MEDIUM
- **Status:** `CONFIRMED`
- **Evidence:**
  - `backend/app/services/auth/sessions.py` lines 89–136 (`rotate_refresh_token`):
    Performs `select(RefreshToken)` without row-level locking (`with_for_update`) or atomic conditional update.
    Under concurrent requests with the same refresh token, both requests can observe `is_revoked == False` and mint new tokens.
- **Affected File/Lines:** `backend/app/services/auth/sessions.py:89-136`
- **Intended Fix:**
  - Use database transaction locking (`with_for_update`) or conditional atomic update (`UPDATE refresh_tokens SET revoked_at = :now WHERE id = :id AND revoked_at IS NULL`).
  - Guarantee exactly one request succeeds and subsequent replays trigger reuse theft invalidation.
- **Acceptance Criteria:**
  - Concurrent requests with identical refresh token yield at most one new token family.
  - Replay is reliably rejected.

---

### F-10 — PII Exposure in Authentication Logs
- **Audit Alias:** `F-10`
- **Reported Severity:** MEDIUM
- **Status:** `CONFIRMED`
- **Evidence:**
  - `backend/app/api/v1/endpoints/auth.py` line 88:
    `logger.info("LOGIN_FAILED: Invalid credentials for email=%s", clean_email)`
  - `backend/app/api/v1/endpoints/auth.py` line 123:
    `logger.info("LOGIN_SUCCESS: Authenticated user_id=%s email=%s", user.id, user.email)`
- **Affected File/Lines:** `backend/app/api/v1/endpoints/auth.py:88, 123`
- **Intended Fix:**
  - Redact raw email addresses from log messages; log only non-sensitive event identifiers, status codes, and user UUIDs (post-authentication).
  - Verify that passwords, tokens, cookies, and sensitive query strings are not logged.
- **Acceptance Criteria:**
  - Tests inspecting captured log records confirm absence of raw email strings on login success and failure paths.

---

### F-11 — Silent Deterministic LLM/Embedding Provider Fallback
- **Audit Alias:** `F-11`
- **Reported Severity:** MEDIUM
- **Status:** `CONFIRMED`
- **Evidence:**
  - `backend/app/services/llm/registry.py` line 38:
    `provider_name = cfg.llm_provider or "deterministic"`
  - `backend/app/services/embeddings/registry.py` lines 23, 36–40:
    Defaults to `DeterministicEmbeddingProvider` if `embedding_provider` setting is blank.
  - `backend/app/core/config.py` lines 255–262: Defaults provider names to empty string `""` without production validation.
- **Affected File/Lines:** `backend/app/services/llm/registry.py:38`, `backend/app/services/embeddings/registry.py:23, 36-40`, `backend/app/core/config.py:255-262`
- **Intended Fix:**
  - Require explicit LLM and embedding provider/model in production mode.
  - Reject empty/mock providers during production startup.
  - Validate configured embedding dimensions against pgvector schema and index dimensions.
- **Acceptance Criteria:**
  - Blank provider in production fails preflight startup validation.
  - Dimension mismatch fails before database indexing.

---

### F-12A — Resource Bounds and Upload Limit Mismatch
- **Audit Alias:** `F-12` (part 1: Limits)
- **Reported Severity:** MEDIUM
- **Status:** `CONFIRMED`
- **Evidence:**
  - Nginx proxy configuration specifies `client_max_body_size 50M;` (`deployment/nginx/nginx.conf:11`, `frontend/nginx.conf:11`).
  - Application configuration specifies `max_upload_size_bytes: int = 26214400` (25 MB in `backend/app/core/config.py:270`).
  - Docker Compose lacks resource limits (CPU/memory) on ingestion workers.
- **Affected File/Lines:** `deployment/nginx/nginx.conf:11`, `frontend/nginx.conf:11`, `backend/app/core/config.py:270`, `docker-compose.yml`
- **Intended Fix:**
  - Reconcile proxy and application upload limits to a single consistent standard (25 MB).
  - Add explicit bounds for document decompression, page counts, chunk limits, and worker concurrency.
- **Acceptance Criteria:**
  - Upload boundary tests verify consistent rejection above the effective limit.

---

### F-12B — Startup Database Migrations & Privilege Separation
- **Audit Alias:** `F-12` (part 2: Database Migrations)
- **Reported Severity:** MEDIUM
- **Status:** `CONFIRMED`
- **Evidence:**
  - `backend/Dockerfile` line 40:
    `CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]`
    Executes database schema migrations on application container start under the application's runtime database role.
- **Affected File/Lines:** `backend/Dockerfile:40`, `backend/alembic/env.py`
- **Intended Fix:**
  - Separate database migrations into an explicit operational step/job.
  - Document least-privilege runtime database user configuration (DML only, no DDL/DROP) for production deployment.
- **Acceptance Criteria:**
  - Application starts safely when schema is up to date; fails gracefully if migrations are pending.
  - Migration execution is decoupled from runtime traffic serving.

---

### F-12C — Supply Chain, Lockfiles, and Automated CI Gates
- **Audit Alias:** `F-12` (part 3: Supply Chain & CI)
- **Reported Severity:** MEDIUM
- **Status:** `CONFIRMED`
- **Evidence:**
  - `backend/` has `requirements.txt` with loose version bounds, but lacks a deterministic lockfile (e.g. `requirements.lock`).
  - Repository lacks automated CI workflow definitions (`.github/workflows/` absent).
  - Security scanning tools (`pip-audit`, `bandit`, `trivy`, `gitleaks`) are not configured in CI.
- **Affected File/Lines:** `backend/requirements.txt`, `.github/`
- **Intended Fix:**
  - Generate and maintain reproducible lockfiles using native tooling.
  - Define CI pipeline specification running automated unit/integration tests, dependency audits, secret scanning, and static checks.
- **Acceptance Criteria:**
  - Reproducible lockfiles committed.
  - CI checks documented with baseline execution commands.

---

## 4. Acceptance Criteria & Release Gates Summary

| Finding | Severity | Status | Chunk | Verifying Test / Proof |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | HIGH | `RESOLVED` | Chunk 1 | `deployment/scripts/verify_env_security.ps1` (exit code 0; FAT32/NTFS detection, untracked `.env`) |
| **F-02** | HIGH | `RESOLVED` | Chunk 2 | `tests/unit/test_dockerignore_isolation.py` (2/2 passed) |
| **F-03** | HIGH | `RESOLVED` | Chunk 3 | `tests/unit/test_backup_security.py` (3/3 passed) |
| **F-04** | HIGH | `RESOLVED` | Chunk 4 | `tests/unit/test_restore_security.py` (5/5 passed) |
| **F-05** | HIGH | `RESOLVED` | Chunk 5 | `tests/unit/test_production_config_hardening.py`, `tests/unit/test_auth_csrf.py` (13/13 passed) |
| **F-06** | HIGH | `RESOLVED` | Chunk 6 | `tests/unit/test_docker_compose_security.py`, `deployment/nginx/tls-proxy.conf.template` (1/1 passed) |
| **F-07** | HIGH | `RESOLVED` | Chunk 5 | `tests/unit/test_production_config_hardening.py` (weak password and unauthenticated Redis rejection) |
| **F-08** | MEDIUM | `RESOLVED` | Chunk 7 | `tests/unit/test_rate_limit.py` (3/3 passed, bounded in-memory fallback) |
| **F-09** | MEDIUM | `RESOLVED` | Chunk 8 | `tests/integration/test_concurrent_refresh_rotation.py` (`with_for_update` row locking) |
| **F-10** | MEDIUM | `RESOLVED` | Chunk 9 | `tests/unit/test_auth_log_privacy.py` (absence of raw emails verified) |
| **F-11** | MEDIUM | `RESOLVED` | Chunk 10 | `tests/unit/test_provider_production_hardening.py` (6/6 passed) |
| **F-12A** | MEDIUM | `RESOLVED` | Chunk 11 | `tests/unit/test_limits_and_migrations.py` (25M body limit alignment) |
| **F-12B** | MEDIUM | `RESOLVED` | Chunk 11 | `tests/unit/test_limits_and_migrations.py`, `docs/deployment/migrations.md` |
| **F-12C** | MEDIUM | `RESOLVED` | Chunk 11 | `backend/requirements.lock`, `.github/workflows/security-ci.yml` |

---

## 5. Automated Verification Results Matrix

- **Backend Unit Tests:** 138 / 138 passed (100%)
- **Backend Integration Tests:** 107 / 107 passed (100%)
- **Frontend Vitest Tests:** 45 / 45 passed (100%)
- **Total Automated Tests:** 290 / 290 passed (100%)
- **Residual Findings:** 0
- **Overall Status:** **READY FOR INDEPENDENT VERIFICATION BY CODEX**

