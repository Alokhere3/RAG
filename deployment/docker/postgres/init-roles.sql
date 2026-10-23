-- =============================================================================
-- Least-Privilege Role Separation for RAG Platform (F-12B)
-- =============================================================================
-- This script is executed by the PostgreSQL superuser (POSTGRES_USER) during
-- container initialization via docker-entrypoint-initdb.d.
--
-- It creates two application-level roles:
--
--   1. rag_migrator — Full DDL privileges for schema migrations (Alembic).
--      Used only during 'alembic upgrade head' in deploy pipelines.
--
--   2. rag_app     — Restricted DML-only privileges for runtime application
--      queries. Prevents the web server from modifying schema structure.
--
-- In development, using the default superuser (POSTGRES_USER) is acceptable.
-- In production, operators should configure:
--   - MIGRATION_DATABASE_URL → pointing to rag_migrator
--   - DATABASE_URL           → pointing to rag_app
--
-- Passwords for these roles MUST be supplied via environment variables in
-- production. The defaults below are development-only placeholders.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Role: rag_migrator (DDL — schema migrations only)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_migrator') THEN
        CREATE ROLE rag_migrator WITH LOGIN PASSWORD 'rag_migrator_dev';
    END IF;
END
$$;

-- Grant schema-level DDL permissions to the migrator role
GRANT ALL PRIVILEGES ON DATABASE rag TO rag_migrator;
GRANT ALL PRIVILEGES ON SCHEMA public TO rag_migrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO rag_migrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO rag_migrator;

-- ---------------------------------------------------------------------------
-- Role: rag_app (DML — runtime application queries only)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_app') THEN
        CREATE ROLE rag_app WITH LOGIN PASSWORD 'rag_app_dev';
    END IF;
END
$$;

-- Grant DML-only permissions to the application runtime role
GRANT CONNECT ON DATABASE rag TO rag_app;
GRANT USAGE ON SCHEMA public TO rag_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rag_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO rag_app;
