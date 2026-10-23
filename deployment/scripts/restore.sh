#!/usr/bin/env bash
# ==============================================================================
# Production Restore Script for RAG Platform
# ==============================================================================
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <path_to_backup_archive.tar.gz>" >&2
    exit 1
fi

ARCHIVE_PATH="$1"

echo "=== Starting Platform Restore ==="
python3 /app/deployment/scripts/restore.py "$ARCHIVE_PATH"
echo "=== Restore Complete & Verified ==="
