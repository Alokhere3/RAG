# Backup, Restore, and Disaster Recovery Runbook

**Target Audience:** DevOps, System Administrators, and Client Infrastructure Engineers.

---

## 1. Architecture Overview

In the self-hosted dedicated deployment model, each client operates an isolated RAG stack with two stateful components:
1. **Relational Database (`rag-postgres`)**: Stores user accounts, sessions, document metadata, chunk text, vector embeddings, ingestion job state, conversations, and audit history.
2. **Persistent Document Storage (`storage_data`)**: Stores original uploaded client source documents (PDF, DOCX, TXT, Markdown).

```text
┌─────────────────────────────────────────────────────────────┐
│                 Client Stateful Infrastructure              │
│                                                             │
│   ┌──────────────────────────┐   ┌──────────────────────┐  │
│   │    PostgreSQL Database   │   │  Persistent Storage  │  │
│   │     (pgvector + data)    │   │  (source documents)  │  │
│   └─────────────┬────────────┘   └──────────┬───────────┘  │
│                 │                           │               │
│                 ▼                           ▼               │
│       ┌───────────────────────────────────────────────┐     │
│       │      deployment/scripts/backup.py             │     │
│       │  - pg_dump / sqlite backup                    │     │
│       │  - storage files snapshot                     │     │
│       │  - SHA-256 checksum manifest generation       │     │
│       │  - Tarball compression (.tar.gz)              │     │
│       └───────────────────────┬───────────────────────┘     │
│                               │                             │
│                               ▼                             │
│       ┌───────────────────────────────────────────────┐     │
│       │   rag_backup_YYYYMMDD_HHMMSSZ.tar.gz          │     │
│       │   ├── manifest.json (signed checksums)        │     │
│       │   ├── database.dump (pg_dump custom format)   │     │
│       │   └── storage/ (raw document files)           │     │
│       └───────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Automated & Scheduled Backups

### Automated Daily Cron Job
On the client host machine or dedicated management runner, configure a daily cron job:

```bash
# Edit crontab for deployment operator
crontab -e

# Take daily backup at 02:00 UTC and retain in /var/backups/rag
0 2 * * * docker compose -f /opt/rag/docker-compose.yml exec -T backend python /app/deployment/scripts/backup.py >> /var/log/rag_backup.log 2>&1
```

### Manual Backup Execution
To take an immediate backup before applying system updates or migrations:

```bash
# Execute backup via running backend container
docker compose exec backend python /app/deployment/scripts/backup.py

# Or run directly on host with appropriate environment variables:
export DATABASE_URL="postgresql+asyncpg://rag:SECRET@localhost:5432/rag"
export STORAGE_DIR="/opt/rag/data/storage"
export BACKUP_OUTPUT_DIR="/var/backups/rag"
python deployment/scripts/backup.py
```

### Manifest Structure
Each backup archive includes a `manifest.json` guaranteeing data integrity:
```json
{
  "backup_id": "rag_backup_20261023_020000Z",
  "created_at": "2026-10-23T02:00:00.123456+00:00",
  "app_version": "0.1.0",
  "database": {
    "type": "postgresql",
    "filename": "database.dump",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "size_bytes": 1420852
  },
  "storage": {
    "file_count": 42,
    "total_bytes": 10528492,
    "files": {
      "doc-uuid-1.pdf": {
        "sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
        "size_bytes": 254120
      }
    }
  }
}
```

---

## 3. Disaster Recovery & Clean Restore Procedure

A backup is not considered valid until a test restore has completed successfully.

### Step 1: Provision Clean Target Environment
Ensure Docker, Postgres, and Redis are running in the target recovery environment.

```bash
docker compose up -d postgres redis
```

### Step 2: Execute Restore Tool
Run the restore script pointing to the backup archive:

```bash
# Inside docker container or recovery host:
python deployment/scripts/restore.py /var/backups/rag/rag_backup_20261023_020000Z.tar.gz
```

The restore script performs the following verification phases:
1. **Archive Check**: Validates gzip integrity and extracts `manifest.json`.
2. **Database Integrity**: Re-computes SHA-256 on `database.dump` and compares against the manifest.
3. **Storage File Integrity**: Re-computes SHA-256 for all extracted storage files.
4. **Database Restoration**: Executes `pg_restore` (or SQLite backup for local environments) cleanly.
5. **Metadata & Storage Consistency Check**: Verifies that every document registered in the database has an identical file matching on disk.

### Step 3: Start Application & Worker Services
```bash
docker compose up -d backend worker frontend
```

### Step 4: Validate Restored Platform
Run the automated pre-flight validator:
```bash
python deployment/scripts/validate_deployment.py
```

Log in to the Web UI as an Administrator and confirm:
1. User accounts and roles are intact.
2. Ingested documents list appears with `READY` status.
3. Asking a test question in Chat returns accurate citations from restored documents.

---

## 4. Backup Retention & Storage Encryption Policy

- **Encryption at Rest**: Backup archives should be encrypted using AES-256 (e.g. `gpg --symmetric --cipher-algo AES256 rag_backup_*.tar.gz`) before transmission to off-site storage.
- **Recommended Retention Schedule**:
  - Daily backups: Retain for 14 days.
  - Weekly backups: Retain for 8 weeks.
  - Monthly backups: Retain for 12 months.
