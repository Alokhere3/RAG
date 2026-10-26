-- =============================================================================
-- PostgreSQL Role Credential Rotation Script (F-12B)
-- =============================================================================
-- Rotates credentials for rag_app and rag_migrator on an active database.
--
-- Responsibilities (Rotation Scope Only):
--   - Updates passwords for rag_app and rag_migrator.
--   - Reconciles role security attributes (NOSUPERUSER, NOINHERIT, etc.).
--   - Revokes any unintended role memberships from rag_app.
--   - Verifies rag_app does not own database, schema, table, routine, or type objects.
--   - Does NOT alter schema ownership or database structure.
--   - Does NOT re-bootstrap grants (preserves existing operational permissions).
--
-- Consumes credentials from process environment via psql's \getenv:
--   - RAG_APP_PASSWORD
--   - RAG_MIGRATOR_PASSWORD
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
-- 1. Rotate Credentials & Enforce Role Attributes
-- ---------------------------------------------------------------------------
ALTER ROLE rag_migrator WITH PASSWORD :'migrator_pass'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT LOGIN;

ALTER ROLE rag_app WITH PASSWORD :'app_pass'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT LOGIN;

-- ---------------------------------------------------------------------------
-- 2. Reconcile Memberships (Revoke All Indirect Privilege Paths)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
BEGIN
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
                RAISE EXCEPTION 'Rotation verification failed: cannot revoke unexpected membership "%" from rag_app because dependent downstream grants exist. Downstream role memberships would be destroyed by cascading. Please inspect pg_auth_members where grantor = ''rag_app''::regrole and resolve manually.', r.rolname;
        END;
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Verify Safe Object Ownership (Fail Closed on Violation)
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
    -- Check database ownership
    SELECT pg_catalog.pg_get_userbyid(datdba) INTO v_db_owner
    FROM pg_database WHERE datname = current_database();
    IF v_db_owner = 'rag_app' THEN
        RAISE EXCEPTION 'Rotation verification failed: database "%" is owned by runtime role rag_app. The runtime role cannot own the database.', current_database();
    END IF;

    -- Check schema ownership
    SELECT nspname INTO v_schema_name
    FROM pg_namespace
    WHERE pg_catalog.pg_get_userbyid(nspowner) = 'rag_app'
      AND nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'
    LIMIT 1;
    IF v_schema_name IS NOT NULL THEN
        RAISE EXCEPTION 'Rotation verification failed: schema "%" is owned by runtime role rag_app. Reassign schema ownership to rag_migrator.', v_schema_name;
    END IF;

    -- Check table / sequence / view / type ownership
    SELECT count(*), min(c.relname) INTO v_object_count, v_sample_object
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE pg_catalog.pg_get_userbyid(c.relowner) = 'rag_app'
      AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';
    IF v_object_count > 0 THEN
        RAISE EXCEPTION 'Rotation verification failed: runtime role rag_app owns % object(s) in database "%" (sample: "%"). Run "REASSIGN OWNED BY rag_app TO rag_migrator;" connected as superuser.', v_object_count, current_database(), v_sample_object;
    END IF;

    -- Check routine ownership
    SELECT count(*), min(p.proname) INTO v_routine_count, v_sample_object
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE pg_catalog.pg_get_userbyid(p.proowner) = 'rag_app'
      AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';
    IF v_routine_count > 0 THEN
        RAISE EXCEPTION 'Rotation verification failed: runtime role rag_app owns % routine(s) in database "%" (sample: "%"). Run "REASSIGN OWNED BY rag_app TO rag_migrator;".', v_routine_count, current_database(), v_sample_object;
    END IF;

    -- Check type ownership (composite, enum, domain, range, multirange)
    SELECT count(*), min(t.typname) INTO v_type_count, v_sample_object
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE pg_catalog.pg_get_userbyid(t.typowner) = 'rag_app'
      AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
      AND t.typtype IN ('c', 'e', 'd', 'r', 'm');
    IF v_type_count > 0 THEN
        RAISE EXCEPTION 'Rotation verification failed: runtime role rag_app owns % type(s) in database "%" (sample: "%"). Run "REASSIGN OWNED BY rag_app TO rag_migrator;".', v_type_count, current_database(), v_sample_object;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 4. Clean up psql variables
-- ---------------------------------------------------------------------------
\unset app_pass
\unset migrator_pass
