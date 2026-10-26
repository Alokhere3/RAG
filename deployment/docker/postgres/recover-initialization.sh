#!/bin/sh
# =============================================================================
# PostgreSQL Initialization Recovery Script for RAG Platform (F-12B)
# =============================================================================
# Use this script when first-time container initialization failed after PostgreSQL
# initialized its data directory (so /docker-entrypoint-initdb.d/ will not run
# automatically again), or to safely repair incomplete role/schema configuration.
#
# DO NOT DELETE PERSISTENT DATABASE VOLUMES (docker compose down -v) ON EXISTING DATABASES!
#
# Accepts credentials via:
#   1. Standard input (streamed lines of KEY=VALUE or KEY="VALUE")
#      Example: grep -E '^RAG_(APP|MIGRATOR)_PASSWORD=' .env | docker compose exec -T postgres /usr/local/bin/recover-initialization.sh
#   2. Interactive prompt when executed in an interactive terminal (read -s)
#   3. Process environment (if explicitly exported in execution context)
#
# Security:
#   - Does not put passwords on command-line arguments (argv / ps aux).
#   - Does not rely on stale container PID 1 environment.
#   - Never logs passwords or echoes them to stdout/stderr.
#   - Delivers secrets to psql via \getenv from process environment.
#   - Safely executes full bootstrap/reconciliation via init-roles.sql.
# =============================================================================

set -eu

RECOVER_APP_PASS=""
RECOVER_MIG_PASS=""

# 1. Check if input is piped through stdin
if [ ! -t 0 ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            RAG_APP_PASSWORD=*|app_pass=*)
                RECOVER_APP_PASS=$(printf '%s' "$line" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
                ;;
            RAG_MIGRATOR_PASSWORD=*|migrator_pass=*)
                RECOVER_MIG_PASS=$(printf '%s' "$line" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
                ;;
        esac
    done
fi

# 2. Fall back to current process environment if set
if [ -z "$RECOVER_APP_PASS" ] && [ -n "${RAG_APP_PASSWORD:-}" ]; then
    RECOVER_APP_PASS="$RAG_APP_PASSWORD"
fi
if [ -z "$RECOVER_MIG_PASS" ] && [ -n "${RAG_MIGRATOR_PASSWORD:-}" ]; then
    RECOVER_MIG_PASS="$RAG_MIGRATOR_PASSWORD"
fi

# 3. If still empty and running in interactive terminal, prompt securely
if [ -t 0 ]; then
    if [ -z "$RECOVER_APP_PASS" ]; then
        printf "Enter password for rag_app: " >&2
        stty -echo 2>/dev/null || true
        read -r RECOVER_APP_PASS
        stty echo 2>/dev/null || true
        printf "\n" >&2
    fi
    if [ -z "$RECOVER_MIG_PASS" ]; then
        printf "Enter password for rag_migrator: " >&2
        stty -echo 2>/dev/null || true
        read -r RECOVER_MIG_PASS
        stty echo 2>/dev/null || true
        printf "\n" >&2
    fi
fi

if [ -z "$RECOVER_APP_PASS" ]; then
    echo "ERROR: Password for rag_app was not provided via stream or input." >&2
    exit 1
fi

if [ -z "$RECOVER_MIG_PASS" ]; then
    echo "ERROR: Password for rag_migrator was not provided via stream or input." >&2
    exit 1
fi

# Locate init-roles.sql
SQL_FILE="/etc/postgresql/init-roles.sql"
if [ ! -f "$SQL_FILE" ]; then
    SQL_FILE="/docker-entrypoint-initdb.d/init-roles.sql"
fi
if [ ! -f "$SQL_FILE" ]; then
    SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
    SQL_FILE="$SCRIPT_DIR/init-roles.sql"
fi

if [ ! -f "$SQL_FILE" ]; then
    echo "ERROR: init-roles.sql not found at expected paths." >&2
    exit 1
fi

PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-$PG_USER}"

echo "Executing role bootstrap and privilege recovery for database '${PG_DB}'..."

# Execute recovery using init-roles.sql with \getenv delivery
RAG_APP_PASSWORD="$RECOVER_APP_PASS" \
RAG_MIGRATOR_PASSWORD="$RECOVER_MIG_PASS" \
psql -v ON_ERROR_STOP=1 \
     --username "$PG_USER" \
     --dbname "$PG_DB" \
     -f "$SQL_FILE"

RECOVER_APP_PASS=""
RECOVER_MIG_PASS=""
unset RECOVER_APP_PASS RECOVER_MIG_PASS RAG_APP_PASSWORD RAG_MIGRATOR_PASSWORD 2>/dev/null || true

echo "PostgreSQL role initialization recovery completed successfully."
