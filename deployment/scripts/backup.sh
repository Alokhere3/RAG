#!/usr/bin/env bash
# ==============================================================================
# Production Backup Script for RAG Platform
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_OUTPUT_DIR:-/backups}"
mkdir -p "$BACKUP_DIR"

echo "=== Starting Platform Backup ==="
python3 /app/deployment/scripts/backup.py
echo "=== Backup Complete ==="
