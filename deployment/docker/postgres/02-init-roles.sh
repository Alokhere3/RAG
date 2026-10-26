#!/bin/sh
# =============================================================================
# PostgreSQL Least-Privilege Role Bootstrap Script (F-12B)
# =============================================================================
# Executed by PostgreSQL container initialization during first boot.
# Consumes configured credentials (RAG_APP_PASSWORD, RAG_MIGRATOR_PASSWORD)
# and securely delivers them to psql via environment variables (\getenv)
# without exposing secrets in process arguments (argv / ps aux).
# =============================================================================

set -eu

if [ -z "${RAG_APP_PASSWORD:-}" ]; then
    echo "ERROR: RAG_APP_PASSWORD environment variable is required for role initialization." >&2
    exit 1
fi

if [ -z "${RAG_MIGRATOR_PASSWORD:-}" ]; then
    echo "ERROR: RAG_MIGRATOR_PASSWORD environment variable is required for role initialization." >&2
    exit 1
fi

# Locate init-roles.sql (mounted alongside this script or in /etc/postgresql)
SQL_FILE="/etc/postgresql/init-roles.sql"
if [ ! -f "$SQL_FILE" ]; then
    SQL_FILE="/docker-entrypoint-initdb.d/init-roles.sql"
fi

if [ ! -f "$SQL_FILE" ]; then
    echo "ERROR: init-roles.sql not found at expected paths." >&2
    exit 1
fi

PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-$PG_USER}"

echo "Configuring PostgreSQL role separation and credentials for database '${PG_DB}'..."

# Execute role initialization using psql.
# Passwords are NOT passed in command-line arguments (-v name=val).
# psql reads RAG_APP_PASSWORD and RAG_MIGRATOR_PASSWORD from process environment via \getenv.
RAG_APP_PASSWORD="$RAG_APP_PASSWORD" \
RAG_MIGRATOR_PASSWORD="$RAG_MIGRATOR_PASSWORD" \
psql -v ON_ERROR_STOP=1 \
     --username "$PG_USER" \
     --dbname "$PG_DB" \
     -f "$SQL_FILE"

echo "PostgreSQL role separation configuration completed successfully."
