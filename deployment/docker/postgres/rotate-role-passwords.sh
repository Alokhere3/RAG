#!/bin/sh
# =============================================================================
# Routine Password Rotation Shell Script for RAG Platform (F-12B)
# =============================================================================
# Rotates PostgreSQL credentials for rag_app and rag_migrator.
#
# Accepts credentials via:
#   1. Standard input (streamed lines of KEY=VALUE or KEY="VALUE")
#      Example: grep -E '^RAG_(APP|MIGRATOR)_PASSWORD=' .env | docker compose exec -T postgres /usr/local/bin/rotate-role-passwords.sh
#   2. Interactive prompt when executed in an interactive terminal (read -s)
#   3. Process environment (if explicitly exported in execution context)
#
# Security:
#   - Does not put passwords on command-line arguments (argv / ps aux).
#   - Does not rely on stale container PID 1 environment.
#   - Never logs passwords or echoes them to stdout/stderr.
#   - Delivers secrets to psql via \getenv from process environment.
#   - Does not modify schema ownership or database structure.
# =============================================================================

set -eu

NEW_APP_PASS=""
NEW_MIG_PASS=""

# 1. Check if input is piped through stdin
if [ ! -t 0 ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            RAG_APP_PASSWORD=*|app_pass=*)
                NEW_APP_PASS=$(printf '%s' "$line" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
                ;;
            RAG_MIGRATOR_PASSWORD=*|migrator_pass=*)
                NEW_MIG_PASS=$(printf '%s' "$line" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
                ;;
        esac
    done
fi

# 2. Fall back to current process environment if set
if [ -z "$NEW_APP_PASS" ] && [ -n "${RAG_APP_PASSWORD:-}" ]; then
    NEW_APP_PASS="$RAG_APP_PASSWORD"
fi
if [ -z "$NEW_MIG_PASS" ] && [ -n "${RAG_MIGRATOR_PASSWORD:-}" ]; then
    NEW_MIG_PASS="$RAG_MIGRATOR_PASSWORD"
fi

# 3. If still empty and running in interactive terminal, prompt securely
if [ -t 0 ]; then
    if [ -z "$NEW_APP_PASS" ]; then
        printf "Enter new password for rag_app: " >&2
        stty -echo 2>/dev/null || true
        read -r NEW_APP_PASS
        stty echo 2>/dev/null || true
        printf "\n" >&2
    fi
    if [ -z "$NEW_MIG_PASS" ]; then
        printf "Enter new password for rag_migrator: " >&2
        stty -echo 2>/dev/null || true
        read -r NEW_MIG_PASS
        stty echo 2>/dev/null || true
        printf "\n" >&2
    fi
fi

if [ -z "$NEW_APP_PASS" ]; then
    echo "ERROR: New password for rag_app was not provided via stream or input." >&2
    exit 1
fi

if [ -z "$NEW_MIG_PASS" ]; then
    echo "ERROR: New password for rag_migrator was not provided via stream or input." >&2
    exit 1
fi

# Locate rotate-role-passwords.sql
SQL_FILE="/etc/postgresql/rotate-role-passwords.sql"
if [ ! -f "$SQL_FILE" ]; then
    SQL_FILE="/docker-entrypoint-initdb.d/rotate-role-passwords.sql"
fi
if [ ! -f "$SQL_FILE" ]; then
    SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
    SQL_FILE="$SCRIPT_DIR/rotate-role-passwords.sql"
fi

if [ ! -f "$SQL_FILE" ]; then
    echo "ERROR: rotate-role-passwords.sql not found at expected paths." >&2
    exit 1
fi

PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-$PG_USER}"

echo "Executing routine password rotation for roles 'rag_app' and 'rag_migrator'..."

# Execute rotation using psql.
# Passwords are NOT passed in command-line arguments (-v name=val).
# psql reads RAG_APP_PASSWORD and RAG_MIGRATOR_PASSWORD from process environment via \getenv.
RAG_APP_PASSWORD="$NEW_APP_PASS" \
RAG_MIGRATOR_PASSWORD="$NEW_MIG_PASS" \
psql -v ON_ERROR_STOP=1 \
     --username "$PG_USER" \
     --dbname "$PG_DB" \
     -f "$SQL_FILE"

# Clean up local secret variables immediately
NEW_APP_PASS=""
NEW_MIG_PASS=""
unset NEW_APP_PASS NEW_MIG_PASS RAG_APP_PASSWORD RAG_MIGRATOR_PASSWORD 2>/dev/null || true

echo "PostgreSQL role password rotation completed successfully."
