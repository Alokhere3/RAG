# RAG Platform Security Remediation Plan

## Gemini implements; Codex independently verifies

**Repository:** `F:\RAG`\
**Deployment model:** one dedicated deployment per client; not shared
multi-tenant SaaS\
**Source of truth:** the uploaded Codex security audit report dated
2026-10-23\
**Current release decision:** **BLOCK RELEASE** until all release gates
in this plan pass

------------------------------------------------------------------------

## 1. Objective and working agreement

Use **Gemini as the implementation agent** and **Codex as an
independent, read-only verification agent**. Work in small, reviewable
chunks. Do not ask Gemini to implement every finding in one giant
change. After each chunk, run the tests available locally, inspect the
diff, and ask Codex to verify the exact changed scope without modifying
files.

The audit report is evidence from a source-level review, not proof that
every issue is exploitable in a deployed environment. The report
explicitly says tests, live requests, security scans, and production
runtime checks were not performed or were unavailable. Treat findings as
**reported findings to validate and remediate**, and label anything that
cannot be verified as **NOT VERIFIED**, never as passed.

### Non-negotiable rules

1.  Work only in `F:\RAG`. Confirm the repository root before editing.
2.  Create a clean Git branch, for example
    `security/remediation-2026-10`, and record the current commit/status
    first. The audit report said the files were untracked and no commit
    was available; preserve a backup or snapshot before restructuring
    anything.
3.  Do not print, paste, commit, or place real secrets in reports,
    prompts, logs, screenshots, or test output. Never ask Gemini or
    Codex to reveal `.env` values.
4.  Do not rotate production credentials blindly. First establish which
    credentials are live and where they are used, then rotate through
    the provider/secret manager and update the deployment.
5.  Gemini may edit only the files in the current chunk's declared
    scope. No opportunistic refactors, dependency upgrades, schema
    changes, or unrelated formatting.
6.  Codex verification must be read-only. It must inspect the diff, run
    only explicitly approved tests/commands if requested, and report
    evidence. It must not fix findings itself.
7.  No destructive restore test against a real database or production
    backup. Use disposable temporary directories, test databases, and
    synthetic secrets.
8.  Every chunk must end with: files changed, rationale, tests run and
    results, tests not run and why, residual risks, and exact commands
    for the next verification.
9.  If the repo differs materially from the audit report, stop and
    reconcile the mismatch before implementing. Do not invent paths or
    force a fix that does not fit the actual code.
10. A green unit test is not a production security sign-off. Production
    deployment configuration, TLS termination, secret storage, and
    operational controls need separate evidence.

------------------------------------------------------------------------

## 2. Audit baseline and caveats

The report recommends **BLOCK RELEASE** and lists six HIGH and six
MEDIUM findings. It also says Python test tooling, Node/npm, and several
security scanners were unavailable; Docker existed but no services were
running. Therefore, the plan includes an initial environment/tooling
gate and requires a final evidence-based Codex audit.

### Reported findings

  ----------------------------------------------------------------------------------
  ID                Severity in       Reported issue         Required outcome
                    report                                   
  ----------------- ----------------- ---------------------- -----------------------
  F-01              HIGH              `.env` ACL reportedly  Restrict file and
                                      grants `Everyone` Full parent-directory
                                      Control                access; assess exposure
                                                             and rotate affected
                                                             credentials if
                                                             warranted

  F-02              HIGH              Backend Docker build   Exclude
                                      context may include    local/runtime/private
                                      `backend/data` and     data from build context
                                      `dev.db`;              and image; verify image
                                      `.dockerignore`        contents
                                      reportedly omits them  

  F-03              HIGH              Backup fallback        Fail closed; never
                                      reportedly writes      serialize a connection
                                      `DATABASE_URL` into    URL or secret as a fake
                                      `database.dump` when   dump
                                      `pg_dump` is           
                                      unavailable            

  F-04              HIGH              Restore uses           Validate archive
                                      `tar.extractall()`     members and manifest
                                      without explicit safe  paths; prevent
                                      extraction and trusts  traversal,
                                      manifest paths         symlink/hardlink abuse,
                                                             and overwrite outside
                                                             the target

  F-05              HIGH              `AUTH_COOKIE_SECURE`   Enforce secure cookies
                                      reportedly defaults    in production, validate
                                      false; Compose may not runtime config, and
                                      inject it;             provide CSRF/origin
                                      production-mode        defenses appropriate to
                                      validation may be      the auth model
                                      bypassed               

  F-06              HIGH              Compose reportedly     Document/enforce the
                                      publishes frontend     TLS edge; prevent
                                      over HTTP port 80 and  direct public plaintext
                                      repository TLS config  access to authenticated
                                      is absent              app traffic

  F-07              HIGH              Production validation  Fail closed on unsafe
                                      reportedly accepts     production
                                      weak DB/Redis          configuration; validate
                                      defaults, Redis has no deployment secrets and
                                      auth/TLS, Compose      provider settings
                                      defaults `APP_ENV` to  before serving traffic
                                      development, preflight 
                                      not wired into         
                                      startup/CI             

  F-08              MEDIUM            Login rate limiting    Make outage behavior
                                      reportedly fails open  explicit, bounded,
                                      on Redis errors        observable, and tested;
                                                             avoid accidentally
                                                             disabling abuse
                                                             protection

  F-09              MEDIUM            Refresh-token rotation Implement
                                      may not be atomic      atomic/conditional
                                      under concurrent       rotation and test
                                      requests               replay/concurrency
                                                             behavior

  F-10              MEDIUM            Login logs reportedly  Remove or safely
                                      include email          pseudonymize PII in
                                      addresses              auth logs; verify
                                                             redaction

  F-11              MEDIUM            Deterministic          Require explicit
                                      LLM/embedding          production
                                      fallbacks may be       provider/model
                                      selected silently when configuration and
                                      provider configuration validate embedding
                                      is blank               dimensions; no silent
                                                             production fallback

  F-12              MEDIUM / report   Report mentions        Reconcile the
                    inconsistency     resource limits,       duplicated report and
                                      upload limit mismatch, assign stable IDs
                                      missing lock/scans/CI; before closure; bound
                                      a duplicated report    resources, align
                                      section separately     limits, add
                                      labels startup         supply-chain gates, and
                                      migrations as F-12     review migration
                                                             privilege/startup
                                                             behavior
  ----------------------------------------------------------------------------------

**Important:** The report has duplicated sections and inconsistent F-12
labeling. Do not assume the identifier alone proves scope. During Chunk
0, create a canonical finding register that maps every distinct
observation to one stable ID, affected file/line, evidence, severity,
and acceptance test. Keep the original audit IDs as aliases where
needed.

------------------------------------------------------------------------

## 3. Execution sequence

Recommended order is deliberately conservative. Complete one chunk,
verify it, and only then proceed.

  ---------------------------------------------------------------------------
  Chunk             Scope              Primary findings  Required checkpoint
  ----------------- ------------------ ----------------- --------------------
  0                 Baseline,          All               No implementation
                    repository                           until baseline and
                    snapshot,                            paths are reconciled
                    canonical finding                    
                    register, tooling                    
                    inventory                            

  1                 `.env` permissions F-01              ACL evidence
                    and secret                           captured without
                    exposure                             secret values; no
                    assessment                           credentials exposed
                                                         in Git

  2                 Docker             F-02              Synthetic canary
                    build-context and                    files absent from
                    image data                           context/image; build
                    isolation                            succeeds

  3                 Backup correctness F-03              Missing `pg_dump`
                    and secret-safe                      causes a safe
                    failure behavior                     nonzero failure; no
                                                         connection URL in
                                                         artifacts

  4                 Restore            F-04              Traversal, link,
                    archive/manifest                     absolute path, and
                    path hardening                       overwrite tests
                                                         rejected

  5                 Production config  F-05, F-07        Production config
                    validation, secure                   fails closed; auth
                    cookies,                             tests pass
                    CSRF/origin                          

  6                 TLS edge and       F-06              Deployment topology
                    plaintext exposure                   proves TLS
                                                         termination and no
                                                         unintended public
                                                         HTTP

  7                 Login limiter      F-08              Defined policy and
                    Redis outage                         outage tests pass
                    policy                               

  8                 Atomic             F-09              Concurrent
                    refresh-token                        refresh/replay tests
                    rotation                             demonstrate
                                                         single-use behavior

  9                 PII-safe           F-10              Captured logs
                    authentication and                   contain no raw
                    error logging                        email, tokens,
                                                         passwords, or
                                                         connection strings

  10                Explicit           F-11              Production fails
                    LLM/embedding                        closed without
                    configuration and                    provider/model;
                    dimensions                           dimensions validated

  11                Resource limits,   F-12 and          Limits
                    upload             migration         documented/tested;
                    consistency,       observation       CI scan and
                    migrations, supply                   migration plan
                    chain                                evidenced

  12                Full regression,   All               Codex reports PASS
                    deployment                           for all release
                    rehearsal,                           gates; otherwise
                    independent final                    remain BLOCK RELEASE
                    audit                                
  ---------------------------------------------------------------------------

If a chunk reveals a cross-cutting dependency, pause and split it into a
separate chunk rather than silently expanding scope.

------------------------------------------------------------------------

## 4. Chunk 0 --- establish a trustworthy baseline

### Gemini implementation prompt

> You are the implementation agent for a security remediation project in
> `F:\RAG`. This is a dedicated self-hosted deployment per client, not a
> shared multi-tenant SaaS platform.
>
> **This chunk is discovery and documentation only. Do not modify
> application code, dependencies, runtime configuration, secrets,
> databases, Docker images, or running services.**
>
> 1.  Confirm the repository root and current Git branch, commit, and
>     status. The previous audit reported no commit and untracked
>     project files; if this is still true, do not discard or overwrite
>     anything. Recommend a safe snapshot/branch workflow and wait if a
>     safe baseline cannot be established.
> 2.  Inventory the actual project structure, runtime versions, package
>     managers, lockfiles, tests, Docker/Compose files, backup/restore
>     scripts, configuration validation, auth/session code,
>     LLM/embedding configuration, CI workflows, and deployment/TLS
>     docs.
> 3.  Do not display `.env` values. You may report whether required keys
>     are present/empty and whether the file is tracked, but redact all
>     values.
> 4.  Reconcile the attached audit's duplicated/inconsistent F-12
>     entries. Produce `security/remediation/finding-register.md` with
>     stable IDs, original audit aliases, severity, evidence (path and
>     line numbers), status (`CONFIRMED`, `NOT CONFIRMED`,
>     `NEEDS RUNTIME EVIDENCE`), intended fix, and a test/acceptance
>     criterion. Do not downgrade a finding merely because it is not
>     reproducible in this environment.
> 5.  Inventory which test and scan commands can actually run. Do not
>     install packages or change dependencies in this chunk. Record
>     unavailable tools as unavailable.
> 6.  Record a baseline command list and expected outputs for later
>     verification.
>
> Output a concise summary and the proposed next chunk. Keep secrets
> redacted. Stop if the working tree cannot be safely protected.

### Codex read-only verification prompt

> Perform a **read-only** verification of Chunk 0 in `F:\RAG`. Do not
> edit or create files and do not fix anything. Confirm the reported
> branch/commit/status, repository paths, lockfiles, test/scanner
> availability, and whether `security/remediation/finding-register.md`
> accurately maps the original audit findings to real code locations. Do
> not print secret values. Flag unsupported assumptions, missing
> findings, inconsistent IDs, and any claim that says PASS without
> evidence. Return PASS/FAIL per item and exact evidence.

### Acceptance criteria

-   Baseline is preserved and working tree changes are understood.
-   Canonical register maps all distinct findings, including the F-12
    ambiguity.
-   No secret values appear in output.
-   No code or dependency changes were made.
-   Codex verifies the register read-only before Chunk 1.

------------------------------------------------------------------------

## 5. Chunk 1 --- `.env` access control and secret exposure (F-01)

### Gemini implementation prompt

> Implement only the approved F-01 remediation after inspecting the real
> repository and deployment environment. Do not read out or copy secret
> values.
>
> 1.  Determine whether `.env` is tracked, ignored, included in any
>     build context, copied into images, or referenced by scripts/logs.
>     Report only metadata and redacted findings.
> 2.  Provide a safe Windows PowerShell procedure to inspect and
>     restrict the ACL on the actual `.env` file and its containing
>     directory to the intended user/service identities. Do not remove
>     access blindly; preserve required operator/service access. Do not
>     run ACL-changing commands until the target identities and access
>     requirements are explicit.
> 3.  If the file was exposed to unauthorized identities or committed,
>     document a credential-by-credential rotation checklist. Never
>     print credentials. Rotate only through the owning service/secret
>     manager and update dependent deployments.
> 4.  Confirm `.env` and local secret files are ignored by Git, and add
>     only safe example placeholders to templates. Do not overwrite an
>     existing `.env`.
> 5.  Add a non-secret verification script or documented commands that
>     fail when `.env` is tracked or has unexpectedly broad permissions
>     where the platform supports checking this reliably. Avoid false
>     claims of portable ACL verification.
> 6.  Do not broaden this chunk into Docker, backup, or
>     production-config changes.
>
> Tests: Git tracking/ignore checks; ACL inspection with expected
> principals; redaction test for diagnostic output. Report actions that
> require an operator rather than executing risky access changes
> automatically.

### Codex verification prompt

> Read-only review of F-01. Inspect `.gitignore`, tracked-file status,
> templates, scripts, and the proposed ACL verification. Do not reveal
> `.env` values and do not change ACLs or rotate credentials. Verify the
> actual ACL evidence separately from source-level checks. Confirm
> whether any secret file is tracked or included by known scripts. Mark
> environment-level ACL/rotation as NOT VERIFIED unless evidence is
> supplied. Return exact commands and PASS/FAIL/NOT VERIFIED per
> criterion.

### Acceptance tests

-   `git ls-files` does not list `.env` or equivalent live secret files.
-   Ignore rules cover the actual local secret filenames without hiding
    safe templates.
-   ACL shows only intended principals with necessary permissions;
    evidence omits file contents.
-   If exposure is confirmed, affected credentials have a documented
    rotation status.
-   Any automated ACL check is platform-specific and does not claim
    success when it cannot inspect the target ACL.

------------------------------------------------------------------------

## 6. Chunk 2 --- Docker build-context and image isolation (F-02)

### Gemini implementation prompt

> Fix only the backend Docker build-context exposure identified by F-02.
>
> 1.  Inspect the actual Docker build context, Dockerfile `COPY`
>     instructions, Compose build paths, `.dockerignore` files, and
>     runtime data paths. Confirm whether `backend/data`, `dev.db`,
>     uploads, indexes, backups, `.env`, `.git`, caches, and test
>     artifacts can enter the context or image.
> 2.  Update the correct `.dockerignore` with narrowly justified
>     exclusions for secrets, local databases, user documents/uploads,
>     vector indexes, backups, caches, and development artifacts.
>     Preserve required source files and dependency manifests.
> 3.  If the Dockerfile copies the entire backend directory, consider a
>     safer explicit-copy strategy only if it fits the actual build. Do
>     not break runtime paths or silently change deployment behavior.
> 4.  Add a deterministic verification test or script using synthetic
>     canary files (never real data) that proves excluded files do not
>     appear in the build context/image. Use a temporary fixture and
>     remove it afterwards.
> 5.  Build the image if Docker is operational. Inspect image
>     layers/filesystem for canary names and known sensitive path
>     patterns without printing secrets.
> 6.  Do not modify database behavior, backup/restore scripts, or app
>     logic.
>
> If Docker is unavailable, implement the source/config fix and report
> image-level validation as NOT RUN rather than PASS.

### Codex verification prompt

> Read-only verification of F-02. Inspect the exact diff, Dockerfile and
> effective build context. Confirm `.dockerignore` applies to the build
> context actually used by Compose. If Docker is available, run the
> approved synthetic-canary image check; do not use real customer data.
> Confirm no accidental exclusion of required source files. Do not
> modify files. Report source-level and image-level results separately.

### Acceptance tests

-   `.env`, local DBs, user content, vector indexes, backups, and canary
    artifacts are excluded from build context unless a specific,
    justified exception exists.
-   Image builds successfully in a Docker-capable environment.
-   Synthetic canaries are absent from the final image.
-   Runtime mounts remain separate from immutable application image
    layers.
-   The build context is no longer broader than necessary.

------------------------------------------------------------------------

## 7. Chunk 3 --- backup fail-closed behavior (F-03)

### Gemini implementation prompt

> Fix only the backup fallback issue. The audit reports that if
> `pg_dump` is unavailable, the script may write `DATABASE_URL` into
> `database.dump` and archive it. Verify the actual script and database
> engine before changing it.
>
> 1.  Remove any fallback that treats a database connection URL,
>     password, or configuration string as database backup content.
> 2.  If the required native backup utility is missing or fails, stop
>     with a clear non-secret error and nonzero exit code. Do not
>     produce a success-looking archive or overwrite a valid prior
>     backup.
> 3.  Ensure partial temporary files are cleaned safely, without
>     deleting prior valid backups.
> 4.  Keep secrets out of filenames, logs, manifests, command output,
>     and exception messages. Avoid shell command construction with
>     untrusted values.
> 5.  Add isolated tests for: backup tool missing; tool returns nonzero;
>     successful synthetic backup; no `DATABASE_URL`/password canary
>     appears in any generated artifact; cleanup after failure.
> 6.  Document required backup utilities and the exact failure behavior.
>     Do not change restore code in this chunk.
>
> Do not run against production or real customer data. If the database
> is not PostgreSQL, choose the appropriate native backup mechanism
> based on repository evidence instead of assuming `pg_dump` is correct.

### Codex verification prompt

> Read-only verification of F-03. Inspect the diff and tests. Confirm
> there is no path that writes `DATABASE_URL` or another credential into
> a fake dump, manifest, archive, or log. Run only isolated tests with
> synthetic canary secrets. Confirm missing/failing backup tools result
> in nonzero exit and no misleading valid archive. Do not access
> production data or modify files.

### Acceptance tests

-   Missing native backup tool: nonzero exit, explicit safe error, no
    success archive.
-   Backup tool failure: partial artifacts cleaned without touching
    previous valid backups.
-   Successful test: output has the expected format and integrity
    metadata.
-   Synthetic connection URL/password canaries are absent from archive
    contents and logs.
-   Backup artifacts are not publicly served and their access/encryption
    policy is documented.

------------------------------------------------------------------------

## 8. Chunk 4 --- safe restore archive and manifest validation (F-04)

### Gemini implementation prompt

> Fix only restore archive/manifest path handling. The audit reports
> unsafe `tar.extractall()` use and insufficient validation of manifest
> paths. Inspect the Python version and exact archive format first.
>
> 1.  Validate every archive member before extraction. Reject absolute
>     paths, drive-qualified paths, UNC paths, `..` traversal,
>     unexpected path types, device entries, and symlinks/hardlinks
>     unless explicitly required and safely constrained.
> 2.  Resolve every destination and verify it remains inside a dedicated
>     temporary restore root. Validate manifest paths with the same
>     containment rule; do not trust the manifest just because it is
>     inside the archive.
> 3.  Use a safe extraction API/filter supported by the actual Python
>     version, plus explicit validation. Do not rely on a
>     version-specific default.
> 4.  Extract to a newly created isolated temporary directory, verify
>     required files/checksums/manifest consistency, and only then
>     perform a clearly separated restore step. Never overwrite
>     arbitrary paths.
> 5.  Make failure atomic where feasible: no partial restore of the live
>     database or files if validation fails. Preserve existing backups
>     and target data.
> 6.  Add adversarial tests for `../` traversal, absolute paths, Windows
>     drive/UNC paths, symlink escape, hardlink escape, malicious
>     manifest path, duplicate/conflicting members, unexpected file
>     types, corrupt archive, and valid archive.
> 7.  Tests must use temporary directories and synthetic data only. Do
>     not restore into a live or production target.
>
> Keep the scope limited to restore security. Report any compatibility
> limitation rather than weakening validation.

### Codex verification prompt

> Perform a read-only security review of F-04. Inspect all archive
> extraction and manifest path code, including indirect helper
> functions. Run the adversarial tests in a disposable temporary
> directory if the environment supports them. Verify no malicious
> archive can create or overwrite a file outside the extraction root and
> no symlink/hardlink can bypass containment. Do not execute a real
> restore and do not modify files. Report test names/results and any
> untested platform behavior.

### Acceptance tests

-   Every malicious archive/manifest case is rejected before external
    writes.
-   No file outside the temporary extraction root is created, modified,
    or deleted.
-   Valid archive round-trip works.
-   Corruption or validation failure leaves the live target unchanged.
-   Tests are deterministic and do not require production credentials.

------------------------------------------------------------------------

## 9. Chunk 5 --- production config, secure cookies, CSRF/origin (F-05, F-07)

### Gemini implementation prompt

> Implement the production configuration hardening for F-05 and F-07
> only. First map the actual configuration loader, environment variable
> names, Compose environment wiring, auth cookie creation,
> login/refresh/logout routes, CORS, and any CSRF/origin protection.
>
> 1.  Define explicit supported environment modes. A production
>     deployment must not silently default to development. Keep local
>     development usable through an explicit development configuration.
> 2.  Add fail-closed production validation for required database/Redis
>     credentials, signing secrets, allowed origins, cookie settings,
>     LLM/embedding provider/model settings, and other values proven
>     necessary by the code. Do not invent configuration keys without
>     checking current code.
> 3.  Reject known unsafe/default/placeholder credentials in production.
>     Do not log the rejected value.
> 4.  Require secure authentication cookies in production (`Secure`,
>     appropriate `HttpOnly`, and an intentional `SameSite` policy
>     consistent with the actual frontend/API topology). Do not blindly
>     choose `SameSite=Strict` if it breaks legitimate flows; document
>     the selected policy.
> 5.  Add CSRF protection appropriate to the session design for
>     cookie-authenticated state-changing endpoints. Validate
>     `Origin`/`Referer` where appropriate and maintain a strict
>     allowlist. CORS alone is not CSRF protection.
> 6.  Ensure refresh/logout cookie behavior is consistent and cookies
>     are cleared with matching attributes.
> 7.  Wire production preflight/config validation into the actual
>     production startup/deployment/CI path so invalid configuration
>     prevents serving traffic. Avoid running migrations as a side
>     effect of an unrelated validation command.
> 8.  Add tests for missing values, placeholder values, development
>     mode, production mode, secure cookie flags, disallowed origin,
>     missing/invalid CSRF proof where required, and valid legitimate
>     flows.
> 9.  Update safe `.env.example` and deployment docs with placeholders
>     only. Never print actual environment values.
>
> Do not change refresh-token atomicity in this chunk; that is Chunk 8.
> Do not claim HTTPS is proven by source code alone; that is Chunk 6.

### Codex verification prompt

> Read-only verification of F-05/F-07. Trace configuration from
> environment/Compose through application startup and auth cookie
> issuance. Verify production cannot start with missing/weak/default
> critical configuration, `APP_ENV` is explicit in production, secure
> cookie flags are enforced, and state-changing cookie-authenticated
> routes have the intended CSRF/origin defense. Run relevant
> unit/integration tests if available. Do not reveal secrets or modify
> files. Distinguish code-level validation from actual deployment
> configuration evidence.

### Acceptance tests

-   Production mode is explicit and never defaults to development.
-   Missing/weak required production settings fail before accepting
    requests.
-   Production auth cookies are Secure and HttpOnly where appropriate,
    with documented SameSite behavior.
-   CSRF/origin defenses are tested for state-changing
    cookie-authenticated routes.
-   CORS allowlisting is strict and is not treated as the only CSRF
    defense.
-   Local development still works when explicitly configured.
-   Startup/preflight does not accidentally run migrations or expose
    secret values.

------------------------------------------------------------------------

## 10. Chunk 6 --- TLS and public HTTP exposure (F-06)

### Gemini implementation prompt

> Address the deployment/TLS concern only. The audit reports Compose
> publishes frontend HTTP port 80 and did not find TLS configuration in
> the repository. Do not assume the production TLS edge is absent;
> establish what the repository and deployment docs prove.
>
> 1.  Document the intended production topology: public TLS reverse
>     proxy/load balancer, internal frontend/API networking, and whether
>     direct container ports are reachable from the internet.
> 2.  Make Compose port binding configurable and default to
>     loopback/internal exposure where that is compatible with the
>     actual deployment. Do not break an intentional local development
>     workflow.
> 3.  If TLS is terminated externally, document required TLS
>     version/certificate renewal/security headers and network/firewall
>     rules that prevent bypassing the TLS edge. Do not place private
>     keys in the image or repository.
> 4.  Add deployment/preflight checks or a checklist to verify HTTPS
>     redirect, valid certificate, HSTS where appropriate, and inability
>     to reach authenticated endpoints over unintended plaintext public
>     routes.
> 5.  Do not claim that application code alone enforces HTTPS. Do not
>     introduce a new proxy product or production topology without
>     recording the operational requirement.
>
> Tests should use a local staging environment or explicit configuration
> checks, never production disruption.

### Codex verification prompt

> Read-only verification of F-06. Inspect Compose port bindings and
> deployment documentation. Separate repository facts from
> operator-provided production evidence. Verify direct HTTP exposure is
> constrained as intended and the documented public URL uses valid
> HTTPS. If no staging endpoint or network evidence is available, mark
> TLS runtime status NOT VERIFIED. Do not modify deployment or firewall
> settings.

### Acceptance tests

-   Intended production topology and trust boundary are documented.
-   Public traffic reaches the application over HTTPS.
-   Direct access to internal/plaintext service ports is blocked or
    intentionally restricted.
-   HTTPS redirect/certificate/security-header checks pass in staging.
-   No private TLS keys are stored in source control or baked into
    images.

------------------------------------------------------------------------

## 11. Chunk 7 --- Redis login rate-limiter outage policy (F-08)

### Gemini implementation prompt

> Fix only the login rate limiter's behavior when Redis is unavailable.
> First inspect the current limiter and all endpoints sharing it.
>
> 1.  Choose and document an explicit policy. For authentication
>     endpoints, do not silently disable rate limiting. Prefer a bounded
>     local fallback only if its limitations are clearly documented, or
>     fail closed with a controlled service-unavailable response if that
>     is safer for this deployment.
> 2.  Avoid unbounded in-memory maps, attacker-controlled key growth,
>     and logging every stack trace during an outage.
> 3.  Return a stable, non-sensitive error and preserve normal behavior
>     when Redis recovers.
> 4.  Add tests for Redis timeout, connection refusal, malformed/error
>     responses, rate limit exceeded, recovery, and simultaneous
>     requests. Assert that errors do not expose stack traces, tokens,
>     or credentials.
> 5.  Add a metric/structured event for limiter degradation without PII
>     and with bounded cardinality.
>
> Do not change token rotation or general Redis configuration in this
> chunk.

### Codex verification prompt

> Read-only review of F-08. Verify the selected outage policy is
> actually implemented and tested, that Redis failure does not silently
> turn off all login protection, and that fallback memory cannot grow
> without bound. Test normal, exceeded, unavailable, and recovery paths
> where feasible. Do not modify files.

### Acceptance tests

-   Redis outage behavior is explicit, predictable, and documented.
-   No silent unlimited login path.
-   Fallback resource use is bounded if a fallback exists.
-   Responses and logs do not expose internals or secrets.
-   Recovery restores normal distributed limiting.

------------------------------------------------------------------------

## 12. Chunk 8 --- atomic refresh-token rotation (F-09)

### Gemini implementation prompt

> Fix only refresh-token rotation concurrency and replay handling.
> Inspect the actual token/session schema, storage, and transaction
> support before choosing a design.
>
> 1.  Make rotation an atomic state transition: a refresh token/session
>     can be consumed at most once. Use a database transaction,
>     conditional update, row lock, compare-and-swap, or another
>     mechanism supported by the current store.
> 2.  Define behavior for two simultaneous refresh requests using the
>     same token. Exactly one must succeed; the other must be rejected
>     without minting a second valid token family. If the existing
>     product intentionally supports a brief grace period, justify and
>     threat-model it before implementing.
> 3.  Ensure token hashes/identifiers, not raw refresh tokens, are
>     stored where the architecture supports it. Do not log tokens.
> 4.  Preserve logout/revocation and expiry behavior. Handle transaction
>     failures safely.
> 5.  Add concurrency tests using the real database engine or a faithful
>     integration fixture. Unit tests that mock away the atomic boundary
>     are not sufficient by themselves.
>
> Do not combine this with general auth refactoring or cookie changes.

### Codex verification prompt

> Read-only verification of F-09. Trace refresh-token validation,
> consumption, replacement, revocation, and persistence. Inspect
> transaction boundaries and run concurrent same-token tests. Verify at
> most one refresh succeeds and replay is rejected. Identify any race
> that remains because tests mock the database. Do not edit code or
> print token material.

### Acceptance tests

-   Two or more concurrent requests with the same refresh token result
    in at most one successful rotation.
-   Replayed, expired, revoked, malformed, or wrong-session tokens are
    rejected.
-   No raw refresh token appears in database records or logs where
    hashing is intended.
-   Login, refresh, logout, and session-expiry regression tests pass.

------------------------------------------------------------------------

## 13. Chunk 9 --- authentication log privacy (F-10)

### Gemini implementation prompt

> Fix only authentication and security logging that exposes email
> addresses or other sensitive identifiers.
>
> 1.  Find login, registration, refresh, password reset, and auth
>     failure log statements. Remove raw email addresses, passwords,
>     access/refresh tokens, authorization headers, cookies, connection
>     URLs, and request bodies from logs.
> 2.  Prefer event names, result codes, request/correlation IDs, and
>     bounded non-sensitive metadata. If user correlation is
>     operationally necessary, propose a keyed, rotating pseudonymous
>     identifier rather than a raw email; do not introduce one without
>     documenting the tradeoff.
> 3.  Add centralized redaction where appropriate, but do not rely on a
>     generic regex if structured fields can be excluded at source.
> 4.  Add tests using synthetic canary values and captured logs to prove
>     sensitive values do not appear. Include exception paths and Redis
>     limiter failures.
> 5.  Keep the patch scoped to logging and redaction. Do not log full
>     request objects for debugging.
>
> Never copy real production log content into the report.

### Codex verification prompt

> Read-only verification of F-10. Search relevant log statements and
> exception handlers; run tests with synthetic
> email/password/token/connection-string canaries and inspect captured
> logs. Verify raw values are absent on success and failure paths. Do
> not modify code or request real logs containing personal data.

### Acceptance tests

-   Raw email addresses are not logged by authentication paths unless an
    explicitly approved exception is documented.
-   Passwords, tokens, cookies, connection strings, and request bodies
    are absent.
-   Tests inspect captured logs rather than merely asserting that a
    redaction helper exists.
-   Error handling remains diagnosable using non-sensitive event IDs and
    codes.

------------------------------------------------------------------------

## 14. Chunk 10 --- explicit LLM/embedding configuration (F-11)

### Gemini implementation prompt

> Fix only silent LLM and embedding fallback selection in production.
> Inspect actual provider abstractions, defaults, model names, embedding
> dimensions, and retrieval index assumptions.
>
> 1.  Make production provider and model selection explicit. Blank or
>     unknown provider configuration must cause a startup/preflight
>     error, not silently choose a deterministic/mock provider.
> 2.  Keep deterministic/mock providers available only in explicit
>     test/development modes and make the selected mode visible without
>     revealing API keys.
> 3.  Validate that the selected embedding provider's output dimension
>     matches the configured vector index/schema and existing stored
>     embeddings. If a dimension change requires re-embedding or index
>     migration, stop and document a separate migration plan; do not
>     silently recreate or corrupt indexes.
> 4.  Validate required provider credentials are present without
>     printing them. Do not make outbound calls during ordinary startup
>     unless the existing design explicitly requires and documents a
>     bounded health check.
> 5.  Add tests for blank provider, unknown provider, missing key, mock
>     provider in production, correct dimensions, mismatched dimensions,
>     and development/test behavior.
> 6.  Document provider data egress and retention assumptions based only
>     on verified configuration/docs; mark unknown vendor terms as
>     requiring operator review.
>
> Do not switch models/providers or incur paid API usage without
> explicit approval.

### Codex verification prompt

> Read-only verification of F-11. Trace provider resolution from
> configuration through runtime calls. Verify production cannot silently
> choose deterministic/mock implementations, missing credentials fail
> safely, and embedding dimension mismatches are caught before
> indexing/querying. Run tests with fake providers and synthetic
> vectors. Do not make paid provider calls or reveal API keys.

### Acceptance tests

-   Production requires an explicit supported provider and model.
-   Mock/deterministic fallbacks require explicit non-production
    configuration.
-   Missing credentials and unknown providers fail closed without
    exposing values.
-   Embedding dimensions are validated against the index and stored
    data.
-   Any dimension migration is planned separately and is never implicit.

------------------------------------------------------------------------

## 15. Chunk 11 --- resource bounds, migrations, and supply chain (F-12 + migration observation)

### Gemini implementation prompt

> Address the canonicalized F-12 items and the audit's separate
> observation that Docker startup runs `alembic upgrade head`. First use
> the canonical finding register to confirm the exact scope. Split this
> chunk further if the repository requires unrelated changes.
>
> **Resource and upload limits** 1. Reconcile the reported 50 MB proxy
> limit and 25 MB application limit. Define one documented effective
> maximum and enforce it at proxy, application, and storage layers. Keep
> request-body limits consistent with allowed multipart overhead. 2.
> Bound worker concurrency, request timeouts, upload size, ingestion
> page/file size, decompression expansion, chunk count, embedding batch
> size, and other high-cost paths based on existing architecture. Avoid
> arbitrary low caps without documenting rationale. 3. Add appropriate
> Docker/Compose CPU, memory, process, and restart settings where
> supported by the deployment model. Document platform/version
> limitations instead of pretending unsupported Compose keys are
> effective.
>
> **Database migrations** 4. Inspect startup behavior and migration
> privileges. Prefer a separate, explicit migration job/step and a
> least-privilege runtime DB role if feasible. Do not remove automatic
> migrations without a safe deployment transition plan. 5. Document
> rollback/forward-only migration behavior and test startup when
> migrations are pending or fail.
>
> **Supply-chain/CI** 6. Determine the actual package managers and
> create or maintain reproducible lockfiles using the correct native
> tooling. Do not fabricate lockfiles or change dependency versions
> merely to satisfy a scanner. 7. Add CI checks appropriate to the stack
> for unit/integration tests, dependency vulnerability scanning, secret
> scanning, Docker image/build-context checks, and static analysis. Pin
> third-party actions/images where practical. 8. Scanners must produce
> actionable output and fail the pipeline on agreed severity thresholds.
> Document suppressions with rationale and expiry; do not suppress
> findings simply to obtain a green build. 9. Add a documented restore
> drill in a disposable environment and resource-bound tests for
> upload/ingestion paths.
>
> Preserve existing deployment behavior unless a tested migration plan
> exists. Do not claim a scanner ran if its tool or network access is
> unavailable.

### Codex verification prompt

> Read-only verification of the canonicalized F-12 and migration
> observation. Inspect proxy/application upload limits, Compose resource
> settings, worker/ingestion bounds, dependency manifests/lockfiles, CI
> workflow, migration startup behavior, and DB roles. Run only available
> tests/scans; record exact versions and results. Verify that
> unsupported platform controls are not presented as effective. Do not
> modify files or install tools. Distinguish implemented controls from
> operational controls that require deployment evidence.

### Acceptance tests

-   Upload limits agree across proxy, app, and storage and have boundary
    tests.
-   Expensive ingestion/embedding operations have documented and tested
    resource bounds.
-   Runtime DB credentials do not have schema-owner privileges unless
    specifically justified.
-   Migration execution is explicit, observable, and tested for
    failure/pending states.
-   Lockfiles and security checks match the actual languages/package
    managers.
-   CI gates and scanner results are evidenced; unavailable scanners
    remain NOT VERIFIED.
-   A disposable backup/restore drill completes and verifies restored
    integrity.

------------------------------------------------------------------------

## 16. Chunk 12 --- final regression and release gate

### Gemini implementation prompt

> Do not add new features in this chunk. Prepare the final remediation
> evidence package for the canonical finding register.
>
> 1.  Run the full test suite and every available approved security
>     scan. Record command, tool version, exit code, and result. Do not
>     mark unavailable tools as passed.
> 2.  Run an application build and Docker build if the tools/services
>     are available.
> 3.  Perform a staging deployment rehearsal with production-mode
>     configuration and synthetic data. Verify health checks,
>     authentication, cookie flags, CSRF/origin defenses, rate limiting,
>     refresh rotation, upload limits, LLM/embedding configuration,
>     backup, and restore.
> 4.  Verify TLS at the public edge and ensure direct plaintext access
>     is blocked as designed. If you cannot access the staging network,
>     provide an operator checklist and mark runtime evidence NOT
>     VERIFIED.
> 5.  Update the finding register with evidence links/paths, test names,
>     and residual risks. Do not change a finding to CLOSED without
>     satisfying its acceptance criteria.
> 6.  Produce a release-readiness report with each gate PASS/FAIL/NOT
>     VERIFIED and a final recommendation. Do not release if any HIGH
>     finding remains open or a required security gate is NOT VERIFIED.
>
> Do not modify production systems or use real customer data.

### Codex final read-only audit prompt

> You are the independent release verifier. Perform a **read-only**
> audit of `F:\RAG` after Gemini's remediation work. Do not modify
> files, install dependencies, change configuration, rotate secrets, run
> migrations, create/delete data, or fix findings.
>
> Review the original audit and canonical finding register. Inspect the
> complete diff and relevant code paths. Run only explicitly available,
> non-destructive tests/scans and staging checks that have been
> approved. Do not print secret values or personal data.
>
> For every original finding and each acceptance criterion, report: -
> Status: `PASS`, `FAIL`, or `NOT VERIFIED`. - Evidence: file/line, test
> name and result, command/exit code, or operator-provided staging
> evidence. - Whether the evidence proves source behavior, container
> contents, or actual deployed behavior. - Any regression, bypass,
> false-positive suppression, missing test, or residual risk.
>
> Specifically verify backup secret-safety, restore traversal/link
> protections, production fail-closed config, cookie/CSRF/origin
> behavior, TLS boundary, Redis limiter outage behavior, refresh-token
> concurrency, log redaction, explicit provider selection, embedding
> dimensions, upload/resource bounds, migration privilege/sequencing,
> and CI/scan gates.
>
> Do not infer a PASS from the existence of a test file. Do not mark
> runtime controls as PASS based on source code alone. Do not accept a
> finding closure without evidence. Finish with a release
> recommendation: `BLOCK RELEASE` or
> `ELIGIBLE FOR STAGING/PRODUCTION REVIEW`. A PASS from this audit is
> not permission to deploy automatically; operator approval is still
> required.

### Final release gates

A release is not eligible for review until all of the following are
true:

-   [ ] No HIGH finding remains open.
-   [ ] Every distinct MEDIUM finding has an implemented fix or an
    explicitly accepted, documented residual risk approved by the owner.
-   [ ] No required security gate is `NOT VERIFIED`.
-   [ ] Unit/integration tests and build pass in the intended deployment
    environment.
-   [ ] Backup and restore have passed in a disposable environment.
-   [ ] Production config fails closed on missing/weak required values.
-   [ ] Auth cookie, CSRF/origin, rate-limit outage, and refresh
    concurrency tests pass.
-   [ ] Image/build-context scan confirms no secrets or local/customer
    data are baked into images.
-   [ ] TLS edge and network exposure have been verified in
    staging/production-equivalent infrastructure.
-   [ ] CI dependency/secret/image/static-analysis gates are enabled and
    results are retained.
-   [ ] Operational owner confirms secret rotation, backup
    encryption/access, monitoring, incident response, and rollback
    procedure.
-   [ ] Codex's final read-only report provides evidence for each
    closure.

------------------------------------------------------------------------

## 17. Standard workflow for every chunk

1.  **Gemini implements one chunk only.**
2.  Review `git diff --check`, `git status`, and the complete diff.
    Confirm no secrets were added.
3.  Run focused tests and record commands/results. Do not run
    destructive commands against live data.
4.  **Codex verifies read-only** using that chunk's prompt.
5.  If Codex reports FAIL or NOT VERIFIED, do not proceed to the next
    dependent chunk. Ask Gemini to address only the specific failed
    criterion in a new, narrow patch.
6.  Re-run the focused tests and repeat the read-only verification.
7.  Commit only the verified chunk after review, using a message that
    identifies the finding IDs.
8.  Update `security/remediation/finding-register.md` with evidence, not
    assertions.
9.  Continue to the next chunk only when its dependencies are satisfied.

### Standard completion report template

For each chunk, require Gemini to return:

-   **Chunk / findings:**
-   **Files changed:**
-   **Behavior changed:**
-   **Tests added:**
-   **Commands run and exit codes:**
-   **Tests not run and why:**
-   **Secret/data safety review:**
-   **Known limitations / residual risks:**
-   **Exact Codex verification request:**
-   **Commit hash (if committed):**

Require Codex to return:

-   **Scope inspected:**
-   **Diff status:** clean / concerns
-   **Acceptance criteria:** PASS / FAIL / NOT VERIFIED, each with
    evidence
-   **Tests/scans actually executed:**
-   **Runtime evidence absent:**
-   **New findings or regressions:**
-   **Recommendation:** proceed / remediate / block release

------------------------------------------------------------------------

## 18. Recommended first action

Start with **Chunk 0 only**. The audit report says the repository had no
commit and project files were untracked, so first establish a
recoverable baseline and reconcile the finding IDs before changing
security-sensitive code. Then proceed in order: F-01, F-02, F-03, F-04,
followed by production configuration/auth and the remaining chunks.

**Do not deploy to a client until the final independent audit and
operational release gates are satisfied.**
