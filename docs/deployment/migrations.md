# Database Migration & Schema Management Runbook (F-12B)

## Overview

In the RAG platform:
- Schema migrations are authored using **Alembic** (`backend/alembic/versions/`).
- In local development, the backend container can run migrations automatically at boot via `RUN_MIGRATIONS_ON_STARTUP=true`.
- In production, running DDL / schema alterations automatically on every web container boot is **strictly discouraged** to avoid concurrency race conditions and to adhere to the principle of least privilege (separating DDL migration credentials from runtime DML application credentials).

---

## 1. Migration Decoupling Architecture

The container entrypoint supports explicit gating:

```dockerfile
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS_ON_STARTUP:-false}\" = \"true\" ]; then alembic upgrade head; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

### Modes of Operation

| Environment | `RUN_MIGRATIONS_ON_STARTUP` | Behavior |
| :--- | :--- | :--- |
| **Development** | `true` | Runs `alembic upgrade head` before booting server for instant developer velocity. |
| **Production** | `false` (default) | Does NOT run migrations on web server boot; expects operator or CI/CD to apply migrations. |

---

## 2. Production Migration Execution Procedures

### Option A: Running Migrations via One-Off Docker Compose Task (Recommended)

Before rolling out new web container versions, run the migration in an isolated ephemeral container:

```bash
docker compose run --rm --no-deps backend alembic upgrade head
```

### Option B: Executing Inside an Active Backend Container

If already running:
```bash
docker compose exec backend alembic upgrade head
```

### Option C: Checking Current Migration Revision

To verify database migration status without applying changes:
```bash
docker compose run --rm --no-deps backend alembic current
```

---

## 3. Database Principle of Least Privilege

For hardened production installations:

1. **Migration User (`rag_migrator`)**:
   - Granted `CREATE`, `ALTER`, `DROP` permissions on the schema.
   - Used only during `alembic upgrade head` in deploy pipelines.
2. **Runtime Application User (`rag_app`)**:
   - Granted `SELECT`, `INSERT`, `UPDATE`, `DELETE` on existing tables.
   - `DATABASE_URL` for the backend web service uses `rag_app`.
   - Prevents SQL injection or compromised application code from dropping or modifying database structure.

### Operational Lifecycle: Bootstrap, Rotation, and Recovery

The database role security model strictly separates three distinct operational responsibilities:

| Operation | Script / Entrypoint | Responsibilities & Scope | State Guarantees |
| :--- | :--- | :--- | :--- |
| **Bootstrap** | `02-init-roles.sh`<br>`init-roles.sql` | Executed by PostgreSQL on fresh volumes. Creates `rag_migrator` and `rag_app`, sets schema `public` ownership to `rag_migrator`, assigns DML grants to `rag_app`, configures future default privileges, enforces role attributes, and revokes all memberships from `rag_app`. | Establishes full least-privilege boundary. Fails if `rag_app` owns objects. |
| **Rotation** | `rotate-role-passwords.sh`<br>`rotate-role-passwords.sql` | Routine credential rotation on running database. Consumes new passwords via stdin/prompt. Updates passwords and re-verifies role attributes, memberships, and zero-ownership. | Strictly credential rotation. Does **not** re-bootstrap schemas, transfer ownership, or alter table grants. |
| **Recovery** | `recover-initialization.sh`<br>`init-roles.sql` | Post-initialization recovery when first bootstrap failed or was incomplete after the PostgreSQL data directory was already initialized. | Re-runs full bootstrap and privilege assignment non-destructively **without deleting persistent volumes**. |

### 1. Initial Container Bootstrap

Bootstrap scripts execute automatically when `/var/lib/postgresql/data` is initialized for the first time:
- **`rag_migrator`**: Owns schema `public`, granted DDL privileges (`INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`). Granted `CONNECT` and `TEMPORARY` on the database.
- **`rag_app`**: Restricted to runtime DML (`NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`). Owns zero objects. All role memberships revoked.

#### Temporary-Table Policy and Compatibility Implications
In standard PostgreSQL, the pseudo-role `PUBLIC` is granted `CONNECT` and `TEMPORARY` on newly created databases by default. Consequently, revoking `TEMPORARY` directly from `rag_app` alone leaves temporary table creation open via `PUBLIC` inheritance.
To enforce a strict least-privilege boundary:
1. `init-roles.sql` explicitly executes `REVOKE TEMPORARY ON DATABASE <dbname> FROM PUBLIC`.
2. `TEMPORARY` is explicitly granted to `rag_migrator` (for migrations and administrative tasks).
3. `CREATE` and `TEMPORARY` are revoked from `rag_app`.
4. **Compatibility Implications:** The runtime application and workers cannot execute `CREATE TEMPORARY TABLE`. This matches the application architecture, where all document ingestion and query handling operate on persistent relational tables or in-memory Redis buffers. If future reporting or bulk ETL extensions require temporary tables, a dedicated reporting role or explicit grant must be configured.

#### Schema Ownership on PostgreSQL 15 & 16
On PostgreSQL 15+, initial database creation assigns the `public` schema ownership to the predefined role `pg_database_owner`. To ensure Alembic migrations can execute DDL without permission issues, `init-roles.sql` checks if the public schema is owned by `pg_database_owner` or the bootstrap superuser (`postgres`, `session_user`, or database owner) and safely transfers ownership to `rag_migrator`. If schema `public` is owned by a distinct operator role, existing ownership is preserved with a warning notice.

Credentials are bound from the process environment using psql's `\getenv` command, ensuring passwords are never exposed in process arguments (`argv` / `ps aux`). Type checks in both bootstrap and rotation verify `rag_app` does not own composite, enum, domain, range (`r`), or multirange (`m`) types.

### 2. Routine Credential Rotation Procedure

Because PostgreSQL only executes `/docker-entrypoint-initdb.d/` on a fresh, uninitialized data volume, and because a running container's environment retains initial variables from startup (PID 1), routine credential rotation must **not** rely on stale container environment or expose plaintext passwords in CLI arguments (`docker compose exec -e ...` or `psql -v ...`).

A dedicated rotation script is mounted at `/usr/local/bin/rotate-role-passwords.sh` (`deployment/docker/postgres/rotate-role-passwords.sh`). It reads updated passwords safely via `stdin` stream or interactive prompt.

#### Safe Rotation via stdin Stream (Recommended)
```bash
# 1. Update RAG_APP_PASSWORD and/or RAG_MIGRATOR_PASSWORD in your production .env file
# 2. Safely stream updated secrets into the dedicated rotation script without CLI argument exposure:
grep -E '^RAG_(APP|MIGRATOR)_PASSWORD=' .env | docker compose exec -T postgres /usr/local/bin/rotate-role-passwords.sh
```

#### Safe Rotation via Interactive Prompt
```bash
docker compose exec -it postgres /usr/local/bin/rotate-role-passwords.sh
```

**Security & Scope Guarantees During Rotation:**
- Dedicated rotation script strictly decouples routine password updates from first-time schema bootstrap.
- Passwords are never passed as command-line arguments (preventing `ps aux` process table leaks and shell history logging).
- Passwords are read from the streamed environment or prompt, bypassing stale container environment variables.
- Secrets are delivered to `psql` via `\getenv` from the rotation process environment.
- Existing object ownership and schema structure are strictly preserved (no unexpected schema ownership transfer).
- Role security attributes (`NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, `NOBYPASSRLS`, `NOINHERIT`) and membership revocations are re-verified.
- Verifies `rag_app` owns zero objects; fails closed if ownership violation is detected.
- Credentials are never echoed in logs or error output.

### 3. Role Reconciliation and Remediation for Existing Databases

In PostgreSQL, an object owner retains implicit DDL privileges over their owned objects regardless of schema-level revocations. To enforce DML-only runtime security:
1. `init-roles.sql` and `rotate-role-passwords.sql` verify that `rag_app` does not own any database, schema, table, sequence, view, routine (function/procedure), or type.
2. If `rag_app` is detected as owning objects (e.g. from an older deployment), the scripts fail closed with a clear error instruction rather than silently transferring ownership.
3. **One-time remediation command for operators:**
   Connect as the PostgreSQL superuser (`postgres`) and reassign all objects to the migration role:
   ```sql
   REASSIGN OWNED BY rag_app TO rag_migrator;
   ```
   After reassigning ownership, re-run the role reconciliation or rotation script.

### 4. Safe Recovery from Failed First Initialization

If initial container startup was interrupted or failed (e.g., container started before required credentials were configured in `.env`), PostgreSQL may have initialized its data directory with `initdb` but halted before role creation scripts ran. Because PostgreSQL will never run `/docker-entrypoint-initdb.d/` again on an initialized data directory, operators must recover the configuration.

> **CRITICAL WARNING:** NEVER delete the persistent volume (`docker compose down -v`) as a routine recovery step on an existing database, as this destroys all stored data!

#### Safe Recovery Procedure (Preserves Data Volume):
1. **Verify Database Connectivity:**
   ```bash
   docker compose exec postgres psql -U postgres -d rag -c "\du"
   ```
2. **If `rag_app` or `rag_migrator` are missing or incompletely configured**, execute the recovery script using streamed credentials:
   ```bash
   grep -E '^RAG_(APP|MIGRATOR)_PASSWORD=' .env | docker compose exec -T postgres /usr/local/bin/recover-initialization.sh
   ```
3. **If object ownership violations are reported**, reassign ownership as superuser:
   ```sql
   REASSIGN OWNED BY rag_app TO rag_migrator;
   ```
   Then re-run `recover-initialization.sh`.


### Environment Variable Configuration

In your production `.env` file, configure separate connection strings:

```bash
# Runtime application role (DML only — SELECT, INSERT, UPDATE, DELETE)
DATABASE_URL=postgresql+asyncpg://rag_app:StrongAppPassword@postgres:5432/rag

# Migration role (DDL — CREATE, ALTER, DROP)
MIGRATION_DATABASE_URL=postgresql+asyncpg://rag_migrator:StrongMigratorPassword@postgres:5432/rag
```

### Production Migration Procedure

```bash
# 1. Apply migrations using the DDL-privileged migrator role
# (Alembic natively consumes MIGRATION_DATABASE_URL configured in .env / compose)
docker compose run --rm --no-deps backend alembic upgrade head

# 2. Verify migration status
docker compose run --rm --no-deps backend alembic current

# 3. Start the application (uses DML-only runtime DATABASE_URL)
docker compose up -d backend worker
```

> **Important:** In production (`APP_ENV=production`), `MIGRATION_DATABASE_URL` is mandatory and
> must be explicitly configured with distinct credentials from `DATABASE_URL`. Fallback to
> `DATABASE_URL` is strictly prohibited in production. In development (`APP_ENV=development`),
> when `MIGRATION_DATABASE_URL` is omitted, it safely falls back to `DATABASE_URL` to facilitate
> developer velocity.

