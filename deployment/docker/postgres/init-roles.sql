-- =============================================================================
-- Least-Privilege Role Bootstrap & Reconciliation for RAG Platform (F-12B)
-- =============================================================================
-- Executed during PostgreSQL container initialization via 02-init-roles.sh,
-- or during recovery via recover-initialization.sh.
--
-- Consumes configured role credentials from the process environment via psql's
-- built-in \getenv command:
--   - RAG_APP_PASSWORD       -> Password for runtime role rag_app
--   - RAG_MIGRATOR_PASSWORD  -> Password for migration role rag_migrator
--
-- Security rules:
--   - No hardcoded fallback passwords.
--   - Passwords are NEVER passed in command-line arguments (-v name=val).
--   - \getenv binds credentials from the process environment into psql variables.
--   - Direct DDL statements use :'var' which safely quotes and escapes SQL literals.
--   - Passwords are NOT interpolated into dollar-quoted strings or set_config.
--   - Reconciles role attributes: rag_app (NOINHERIT, NOSUPERUSER, etc.), rag_migrator (INHERIT).
--   - Revokes ALL memberships from rag_app (preventing SET ROLE and indirect privileges).
--   - Fails closed if rag_app owns database, schemas, tables, sequences, views, routines, or types.
--   - Idempotently establishes schema ownership, grants, and default privileges.
--   - Clears credentials from psql variables before completion (\unset).
-- =============================================================================

\getenv app_pass RAG_APP_PASSWORD
\getenv migrator_pass RAG_MIGRATOR_PASSWORD

\if :{?app_pass}
\else
  \echo 'FATAL: Environment variable RAG_APP_PASSWORD is not set.'
  \q 1
\endif

\if :{?migrator_pass}
\else
  \echo 'FATAL: Environment variable RAG_MIGRATOR_PASSWORD is not set.'
  \q 1
\endif

-- ---------------------------------------------------------------------------
-- 1. Create Roles If Missing and Reconcile Attributes & Passwords
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_migrator') THEN
        CREATE ROLE rag_migrator;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_app') THEN
        CREATE ROLE rag_app;
    END IF;
END
$$;

-- Enforce explicit attributes and bind passwords as safely quoted literals
ALTER ROLE rag_migrator WITH LOGIN PASSWORD :'migrator_pass'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;

ALTER ROLE rag_app WITH LOGIN PASSWORD :'app_pass'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

-- ---------------------------------------------------------------------------
-- 2. Reconcile Role Memberships (Eliminate All Indirect Privilege Paths)
-- ---------------------------------------------------------------------------
-- Allowed Membership Policy:
-- Both rag_app (runtime role) and rag_migrator (migration DDL role) are dedicated
-- terminal roles. Neither role is permitted to hold membership in any other role
-- (parent membership count must be zero).
--
-- Restrictive Revocation:
-- Revocations use RESTRICT (not CASCADE). If rag_app or rag_migrator was granted
-- a parent role WITH ADMIN OPTION and subsequently granted that role to downstream
-- roles, a CASCADE revocation would silently destroy those downstream grants.
-- Using RESTRICT traps dependent grants and raises an actionable diagnostic
-- requiring explicit operator remediation before proceeding.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
BEGIN
    -- Revoke ALL role memberships from rag_app to eliminate any indirect privilege
    -- inheritance, administrative authority, or permission to SET ROLE to other roles.
    FOR r IN (
        SELECT r_parent.rolname
        FROM pg_roles r_parent
        JOIN pg_auth_members m ON m.roleid = r_parent.oid
        JOIN pg_roles r_app ON m.member = r_app.oid
        WHERE r_app.rolname = 'rag_app'
    ) LOOP
        BEGIN
            EXECUTE format('REVOKE %I FROM rag_app RESTRICT', r.rolname);
        EXCEPTION
            WHEN dependent_privilege_descriptors_still_exist THEN
                RAISE EXCEPTION 'Role reconciliation failed: cannot revoke unexpected membership "%" from rag_app because dependent downstream grants exist. Downstream role memberships would be destroyed by cascading. Please inspect pg_auth_members where grantor = ''rag_app''::regrole and resolve manually.', r.rolname;
        END;
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- 2b. Reconcile rag_migrator Memberships
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    v_unexpected_count int := 0;
    v_sample_role text;
BEGIN
    -- rag_migrator must not be a member of any other role (it is a peer role,
    -- not a group member). Detect and remove any unexpected memberships using RESTRICT.
    FOR r IN (
        SELECT r_parent.rolname
        FROM pg_roles r_parent
        JOIN pg_auth_members m ON m.roleid = r_parent.oid
        JOIN pg_roles r_mig ON m.member = r_mig.oid
        WHERE r_mig.rolname = 'rag_migrator'
    ) LOOP
        v_unexpected_count := v_unexpected_count + 1;
        v_sample_role := r.rolname;
        RAISE NOTICE 'Removing unexpected rag_migrator membership: REVOKE % FROM rag_migrator RESTRICT', r.rolname;
        BEGIN
            EXECUTE format('REVOKE %I FROM rag_migrator RESTRICT', r.rolname);
        EXCEPTION
            WHEN dependent_privilege_descriptors_still_exist THEN
                RAISE EXCEPTION 'Role reconciliation failed: cannot revoke unexpected membership "%" from rag_migrator because dependent downstream grants exist. Downstream role memberships would be destroyed by cascading. Please inspect pg_auth_members where grantor = ''rag_migrator''::regrole and resolve manually before initialization.', r.rolname;
        END;
    END LOOP;
    IF v_unexpected_count > 0 THEN
        RAISE WARNING
            'rag_migrator held % unexpected membership(s) (sample: "%") that have been revoked. '
            'Review how these memberships were granted to prevent privilege escalation.',
            v_unexpected_count, v_sample_role;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Verify Safe Object Ownership (Prevent DML-Bypass via Ownership)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_db_owner text;
    v_schema_name text;
    v_object_count int;
    v_routine_count int;
    v_type_count int;
    v_sample_object text;
BEGIN
    -- 1. Check database ownership
    SELECT pg_catalog.pg_get_userbyid(datdba) INTO v_db_owner
    FROM pg_database WHERE datname = current_database();
    IF v_db_owner = 'rag_app' THEN
        RAISE EXCEPTION 'Role reconciliation failed: database "%" is owned by runtime role rag_app. The runtime role cannot own the database. Please reassign database ownership to an administrative role before proceeding.', current_database();
    END IF;

    -- 2. Check schema ownership
    SELECT nspname INTO v_schema_name
    FROM pg_namespace
    WHERE pg_catalog.pg_get_userbyid(nspowner) = 'rag_app'
      AND nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'
    LIMIT 1;
    IF v_schema_name IS NOT NULL THEN
        RAISE EXCEPTION 'Role reconciliation failed: schema "%" is owned by runtime role rag_app. The runtime role cannot own schemas. Reassign schema ownership to rag_migrator or an administrative role.', v_schema_name;
    END IF;

    -- 3. Check table / sequence / view / materialized view / foreign table ownership
    SELECT count(*), min(c.relname) INTO v_object_count, v_sample_object
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE pg_catalog.pg_get_userbyid(c.relowner) = 'rag_app'
      AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';
    IF v_object_count > 0 THEN
        RAISE EXCEPTION 'Role reconciliation failed: runtime role rag_app owns % object(s) in database "%" (sample: "%"). Runtime role cannot own database objects without violating DML-only isolation. Run "REASSIGN OWNED BY rag_app TO rag_migrator;" connected as superuser to safely remediate before initialization.', v_object_count, current_database(), v_sample_object;
    END IF;

    -- 4. Check routine (function / procedure / aggregate) ownership
    SELECT count(*), min(p.proname) INTO v_routine_count, v_sample_object
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE pg_catalog.pg_get_userbyid(p.proowner) = 'rag_app'
      AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';
    IF v_routine_count > 0 THEN
        RAISE EXCEPTION 'Role reconciliation failed: runtime role rag_app owns % routine(s) in database "%" (sample: "%"). Runtime role cannot own routines. Run "REASSIGN OWNED BY rag_app TO rag_migrator;" connected as superuser before initialization.', v_routine_count, current_database(), v_sample_object;
    END IF;

    -- 5. Check user-defined type / domain / range / multirange ownership
    SELECT count(*), min(t.typname) INTO v_type_count, v_sample_object
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE pg_catalog.pg_get_userbyid(t.typowner) = 'rag_app'
      AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
      AND t.typtype IN ('c', 'e', 'd', 'r', 'm');
    IF v_type_count > 0 THEN
        RAISE EXCEPTION 'Role reconciliation failed: runtime role rag_app owns % type(s) in database "%" (sample: "%"). Runtime role cannot own user-defined types. Run "REASSIGN OWNED BY rag_app TO rag_migrator;" connected as superuser before initialization.', v_type_count, current_database(), v_sample_object;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 4. Database Connection Privileges (Dynamic current_database())
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_dbname text := current_database();
BEGIN
    -- Revoke inherited temporary table privilege from PUBLIC (PostgreSQL default grant)
    EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', v_dbname);
    EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO rag_migrator', v_dbname);
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rag_app', v_dbname);
    EXECUTE format('REVOKE CREATE, TEMPORARY ON DATABASE %I FROM rag_app', v_dbname);
END
$$;

-- ---------------------------------------------------------------------------
-- 5. Schema Ownership & DDL Authority for rag_migrator
-- ---------------------------------------------------------------------------
-- Assign public schema ownership to rag_migrator on initial bootstrap.
-- Does NOT unconditionally transfer if owned by another non-bootstrap role.
DO $$
DECLARE
    v_public_owner text;
    v_db_owner text;
    r RECORD;
BEGIN
    SELECT pg_catalog.pg_get_userbyid(nspowner) INTO v_public_owner
    FROM pg_namespace WHERE nspname = 'public';

    SELECT pg_catalog.pg_get_userbyid(datdba) INTO v_db_owner
    FROM pg_database WHERE datname = current_database();

    IF v_public_owner <> 'rag_migrator' THEN
        -- On fresh PostgreSQL 15/16 clusters, schema public is typically owned by
        -- 'pg_database_owner' or the bootstrap superuser ('postgres', session_user, v_db_owner).
        -- Safely assign schema public ownership to rag_migrator only when owned by one of
        -- these standard initial bootstrap owners.
        IF v_public_owner IN (session_user, current_user, v_db_owner, 'pg_database_owner', 'postgres') THEN
            ALTER SCHEMA public OWNER TO rag_migrator;
        ELSE
            RAISE NOTICE 'Schema public is owned by "%"; preserving existing operator ownership.', v_public_owner;
        END IF;
    END IF;

    -- Reassign existing objects in schema public owned by standard initial bootstrap owners
    -- to rag_migrator so migration DDL (ALTER TABLE, etc.) can be performed by rag_migrator.
    -- Table-linked serial/identity sequences are automatically transferred when their parent
    -- table owner is changed; only standalone sequences need explicit ALTER SEQUENCE.
    FOR r IN (
        SELECT c.relname, c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND (
              c.relkind IN ('r', 'p', 'v', 'm')
              OR (c.relkind = 'S' AND NOT EXISTS (
                  SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype IN ('a', 'i')
              ))
          )
          AND pg_catalog.pg_get_userbyid(c.relowner) IN (session_user, current_user, v_db_owner, 'pg_database_owner', 'postgres')
    ) LOOP
        IF r.relkind IN ('r', 'p') THEN
            EXECUTE format('ALTER TABLE public.%I OWNER TO rag_migrator', r.relname);
        ELSIF r.relkind = 'S' THEN
            EXECUTE format('ALTER SEQUENCE public.%I OWNER TO rag_migrator', r.relname);
        ELSIF r.relkind = 'v' THEN
            EXECUTE format('ALTER VIEW public.%I OWNER TO rag_migrator', r.relname);
        ELSIF r.relkind = 'm' THEN
            EXECUTE format('ALTER MATERIALIZED VIEW public.%I OWNER TO rag_migrator', r.relname);
        END IF;
    END LOOP;

    -- Revoke CREATE on schema public from PUBLIC pseudo-role.
    -- PostgreSQL versions < 15 grant CREATE on schema public to PUBLIC by default.
    -- PostgreSQL 15+ revoked this, but existing databases upgraded from older
    -- versions may still carry the grant. Revoke unconditionally to enforce
    -- least-privilege: only rag_migrator may create objects in schema public.
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;
END
$$;

GRANT ALL ON SCHEMA public TO rag_migrator;
GRANT ALL ON ALL TABLES IN SCHEMA public TO rag_migrator;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO rag_migrator;

-- ---------------------------------------------------------------------------
-- 6. Runtime DML-Only Permissions for rag_app
-- ---------------------------------------------------------------------------
-- Allow name resolution within schema public, but strictly forbid DDL creation
GRANT USAGE ON SCHEMA public TO rag_app;
REVOKE CREATE ON SCHEMA public FROM rag_app;

-- Existing objects (if any tables or sequences already exist)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rag_app;
REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM rag_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rag_app;

-- ---------------------------------------------------------------------------
-- 7. Default Privileges for Future Objects Created by Migrations
-- ---------------------------------------------------------------------------
-- When rag_migrator creates new tables via Alembic migrations, grant DML to rag_app
ALTER DEFAULT PRIVILEGES FOR ROLE rag_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rag_app;

ALTER DEFAULT PRIVILEGES FOR ROLE rag_migrator IN SCHEMA public
    REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM rag_app;

ALTER DEFAULT PRIVILEGES FOR ROLE rag_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO rag_app;

-- Also apply default privileges if superuser creates objects during init
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rag_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM rag_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO rag_app;

-- ---------------------------------------------------------------------------
-- 8. Clean up psql variables
-- ---------------------------------------------------------------------------
\unset app_pass
\unset migrator_pass
