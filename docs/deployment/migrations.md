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

### Role Creation

The `deployment/docker/postgres/init-roles.sql` script automatically creates both roles
during initial container startup. For existing databases, run the script manually:

```bash
docker compose exec postgres psql -U rag -d rag -f /docker-entrypoint-initdb.d/02-init-roles.sql
```

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
docker compose run --rm --no-deps \
  -e DATABASE_URL="${MIGRATION_DATABASE_URL}" \
  backend alembic upgrade head

# 2. Verify migration status
docker compose run --rm --no-deps backend alembic current

# 3. Start the application (uses DML-only runtime DATABASE_URL)
docker compose up -d backend worker
```

> **Note:** When `MIGRATION_DATABASE_URL` is empty, the backend falls back to
> `DATABASE_URL` for migrations. This is the default behavior in development.

